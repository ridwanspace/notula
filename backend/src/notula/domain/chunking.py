"""Long-audio chunk planning and transcript merging.

Long recordings are split into overlapping chunks, transcribed independently,
then merged. Boundaries snap to detected silences when one falls close enough,
because cutting mid-sentence hurts both transcription and diarization.

Known limitation (kept, not hidden): cross-chunk speaker identity is best-effort.
Generic labels ("Speaker 1") are reconciled by matching utterance text inside the
overlap window; if a speaker never talks during an overlap, chunks cannot prove
the identity and the label is renumbered as a new speaker.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from notula.domain.models import Transcript, Utterance

DEFAULT_MAX_CHUNK_SECONDS = 20 * 60.0
DEFAULT_OVERLAP_SECONDS = 15.0
DEFAULT_SNAP_WINDOW_SECONDS = 30.0

_GENERIC_SPEAKER = re.compile(r"^speaker\s*\d+$", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


def plan_chunks(
    duration_seconds: float,
    *,
    max_chunk_seconds: float = DEFAULT_MAX_CHUNK_SECONDS,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
    snap_window_seconds: float = DEFAULT_SNAP_WINDOW_SECONDS,
    silence_points: Sequence[float] = (),
) -> tuple[Chunk, ...]:
    """Plan overlapping chunk windows over an audio timeline.

    Boundaries are placed every ``max_chunk_seconds``, snapped backwards onto the
    closest silence point within ``snap_window_seconds`` when one exists. Every
    chunk after the first starts ``overlap_seconds`` before the previous boundary
    so the merge step has a shared window to reconcile speakers and drop
    duplicated utterances.
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if overlap_seconds < 0 or overlap_seconds >= max_chunk_seconds / 2:
        raise ValueError("overlap_seconds must be >= 0 and well below max_chunk_seconds")
    if snap_window_seconds >= max_chunk_seconds / 2:
        raise ValueError("snap_window_seconds must be well below max_chunk_seconds")

    if duration_seconds <= max_chunk_seconds:
        return (Chunk(0, 0.0, duration_seconds),)

    silences = sorted(s for s in silence_points if 0 < s < duration_seconds)
    boundaries: list[float] = []
    cursor = 0.0
    while duration_seconds - cursor > max_chunk_seconds:
        target = cursor + max_chunk_seconds
        snapped = max(
            (s for s in silences if target - snap_window_seconds <= s <= target),
            default=target,
        )
        boundaries.append(snapped)
        cursor = snapped

    chunks: list[Chunk] = []
    for i, end in enumerate([*boundaries, duration_seconds]):
        start = 0.0 if i == 0 else boundaries[i - 1] - overlap_seconds
        chunks.append(Chunk(i, start, end))
    return tuple(chunks)


def _normalize(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


def _next_generic_label(existing: set[str]) -> str:
    n = 1
    while f"Speaker {n}" in existing:
        n += 1
    return f"Speaker {n}"


def _map_speakers(
    accumulated: Sequence[Utterance],
    part: Sequence[Utterance],
    overlap_start: float,
    overlap_end: float,
) -> dict[str, str]:
    """Map the incoming chunk's generic speaker labels onto accumulated ones.

    Named speakers map to themselves. Generic labels are matched by normalized
    utterance text within the shared overlap window; anything unmatched becomes
    a fresh globally-unique generic label.
    """
    known = {u.speaker for u in accumulated}
    prev_overlap = {
        _normalize(u.text): u.speaker
        for u in accumulated
        if overlap_start <= u.start_seconds <= overlap_end and u.text.strip()
    }
    mapping: dict[str, str] = {}
    for u in part:
        if u.speaker in mapping or not _GENERIC_SPEAKER.match(u.speaker):
            continue
        if overlap_start <= u.start_seconds <= overlap_end:
            matched = prev_overlap.get(_normalize(u.text))
            if matched is not None:
                mapping[u.speaker] = matched
    for u in part:
        if _GENERIC_SPEAKER.match(u.speaker) and u.speaker not in mapping:
            fresh = _next_generic_label(known | set(mapping.values()))
            mapping[u.speaker] = fresh
    return mapping


def merge_transcripts(
    parts: Sequence[tuple[Chunk, Transcript]],
    *,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
) -> Transcript:
    """Merge per-chunk transcripts (chunk-relative timestamps) into one timeline.

    Inside each overlap window, utterances before its midpoint come from the
    earlier chunk and utterances after it from the later chunk, so duplicated
    speech at the seam is dropped exactly once.
    """
    if not parts:
        raise ValueError("no transcript parts to merge")

    ordered = sorted(parts, key=lambda p: p[0].index)
    merged: list[Utterance] = []
    for chunk, transcript in ordered:
        absolute = [
            Utterance(chunk.start_seconds + u.start_seconds, u.speaker, u.text)
            for u in transcript.utterances
        ]
        if chunk.index == 0:
            merged.extend(absolute)
            continue
        overlap_start = chunk.start_seconds
        overlap_end = chunk.start_seconds + overlap_seconds
        mapping = _map_speakers(merged, absolute, overlap_start, overlap_end)
        midpoint = (overlap_start + overlap_end) / 2
        merged = [u for u in merged if u.start_seconds < midpoint]
        merged.extend(
            Utterance(u.start_seconds, mapping.get(u.speaker, u.speaker), u.text)
            for u in absolute
            if u.start_seconds >= midpoint
        )

    merged.sort(key=lambda u: u.start_seconds)
    return Transcript(utterances=tuple(merged), duration_seconds=ordered[-1][0].end_seconds)
