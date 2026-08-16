"""Deterministic offline providers: same input bytes, same output, zero network.

The demo recording ships with a bundled fixture transcript keyed by the file's
content hash; any other audio gets a transcript synthesized from a seeded RNG,
so the whole pipeline (and every test) runs with no API key at all.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from importlib import resources
from pathlib import Path

from notula.application.ports import Completion, TranscriptionResult
from notula.domain.costing import estimate_audio_tokens
from notula.domain.models import TokenUsage, Transcript, Utterance
from notula.domain.parsing import transcript_from_dict

_LINE = re.compile(r"^\[(\d\d):(\d\d)\] (.+?): (.+)$")


def _digest(path: Path) -> str:
    # Sync read of a local file (ASYNC240).
    return hashlib.sha256(path.read_bytes()).hexdigest()


_SPEAKERS = ("Rina", "Speaker 2", "Dimas")

_TEMPLATES = (
    "We agreed to move the release review to Thursday.",
    "Rina will update the onboarding checklist after this call.",
    "Saya masih menunggu feedback dari tim QA untuk build terakhir.",
    "The staging environment was down for about an hour yesterday.",
    "Can we confirm who owns the migration runbook?",
    "Menurut saya kita perlu extend timeline satu minggu.",
    "Let's keep the scope unchanged for this sprint.",
    "I pushed the fix for the export bug this morning.",
    "Dimas akan follow up dengan vendor soal invoice.",
    "The customer demo went fine, only minor layout issues.",
)


def _fixture_transcript(digest: str) -> Transcript | None:
    fixture = resources.files("notula.infrastructure.providers").joinpath(f"fixtures/{digest}.json")
    if not fixture.is_file():
        return None
    payload: dict[str, object] = json.loads(fixture.read_text(encoding="utf-8"))
    duration = float(payload["duration_seconds"])  # type: ignore[arg-type]
    return transcript_from_dict(payload, duration_seconds=duration)


def _synthesize(digest: str, duration_seconds: float) -> Transcript:
    rng = random.Random(int(digest[:16], 16))  # noqa: S311 - deterministic mock, not crypto
    count = max(4, int(duration_seconds // 7))
    utterances: list[Utterance] = []
    clock = 1.0
    for _ in range(count):
        utterances.append(
            Utterance(
                start_seconds=round(clock, 1),
                speaker=_SPEAKERS[rng.randrange(len(_SPEAKERS))],
                text=_TEMPLATES[rng.randrange(len(_TEMPLATES))],
            )
        )
        clock += rng.uniform(6.0, 8.0)
    duration = duration_seconds if duration_seconds > 0 else clock
    return Transcript(utterances=tuple(utterances), duration_seconds=duration)


class MockTranscriber:
    @property
    def model(self) -> str:
        return "mock"

    async def transcribe(
        self, path: Path, *, roster: str, duration_seconds: float
    ) -> TranscriptionResult:
        digest = _digest(path)
        transcript = _fixture_transcript(digest) or _synthesize(digest, duration_seconds)
        total_chars = sum(len(u.text) for u in transcript.utterances)
        usage = TokenUsage(
            input_tokens=estimate_audio_tokens(transcript.duration_seconds),
            output_tokens=total_chars // 4,
        )
        return TranscriptionResult(transcript=transcript, usage=usage, model="mock")


def _distinct(texts: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for text in texts:
        seen.setdefault(text, None)
    return list(seen)


class MockCompleter:
    @property
    def model(self) -> str:
        return "mock"

    async def complete_json(self, system: str, user: str) -> Completion:
        matches = [_LINE.match(line) for line in user.splitlines()]
        lines = [(m.group(3), m.group(4)) for m in matches if m]
        texts = [text for _, text in lines]
        payload: dict[str, object] = {
            "title": " ".join(texts[0].split()[:6]) if texts else "Meeting summary",
            "tldr": " ".join(texts[:2]) if texts else "No transcript content.",
            "key_points": _distinct(texts)[:3],
            "decisions": [
                text
                for text in texts
                if any(k in text.lower() for k in ("agreed", "decide", "putus"))
            ],
            "action_items": [
                {"task": text, "owner": speaker, "due": None}
                for speaker, text in lines
                if " will " in f" {text.lower()}" or " akan " in f" {text.lower()}"
            ],
            "open_questions": [text for text in texts if text.rstrip().endswith("?")],
        }
        rendered = json.dumps(payload, ensure_ascii=False)
        return Completion(
            text=rendered,
            usage=TokenUsage(input_tokens=len(user) // 4, output_tokens=len(rendered) // 4),
            model="mock",
        )
