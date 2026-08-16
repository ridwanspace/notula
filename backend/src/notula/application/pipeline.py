"""The two-pass meeting pipeline.

Pass 1 (normalize + transcribe) produces the transcript — the system of record.
Pass 2 (summarize) derives a summary from it and can be re-run later via
``resummarize`` without touching the audio again.
"""

from __future__ import annotations

import time
from pathlib import Path

from notula.application.errors import MeetingNotFoundError, MeetingNotReadyError
from notula.application.events import (
    completed_event,
    error_event,
    progress_event,
    stage_event,
    state_event,
)
from notula.application.ports import (
    MeetingRecord,
    PipelineDeps,
    StoredSummary,
    TranscriptionResult,
)
from notula.application.summarize import summarize_transcript
from notula.domain.chunking import Chunk, merge_transcripts, plan_chunks
from notula.domain.costing import cost_usd
from notula.domain.models import (
    StageReport,
    SummaryLanguage,
    TokenUsage,
    Transcript,
)
from notula.domain.state import MeetingState, transition


async def create_meeting(
    deps: PipelineDeps,
    *,
    meeting_id: str,
    filename: str,
    audio_path: str,
    roster: str,
    language: SummaryLanguage,
) -> MeetingRecord:
    record = MeetingRecord(
        id=meeting_id,
        filename=filename,
        state=MeetingState.UPLOADED,
        language=language,
        roster=roster,
        audio_path=audio_path,
        created_at=deps.clock.now(),
    )
    await deps.repo.add(record)
    await deps.bus.publish(meeting_id, state_event(record.state.value))
    return record


async def _advance(
    deps: PipelineDeps,
    meeting_id: str,
    current: MeetingState,
    target: MeetingState,
    *,
    duration_seconds: float | None = None,
) -> MeetingState:
    new_state = transition(current, target)
    await deps.repo.set_state(meeting_id, new_state, duration_seconds=duration_seconds)
    await deps.bus.publish(meeting_id, state_event(new_state.value))
    return new_state


async def _report_stage(deps: PipelineDeps, meeting_id: str, report: StageReport) -> None:
    await deps.repo.add_stage_report(meeting_id, report)
    await deps.bus.publish(
        meeting_id,
        stage_event(report.stage, report.seconds, report.cost_usd, report.detail),
    )


async def _transcribe_chunks(
    deps: PipelineDeps,
    meeting_id: str,
    normalized: Path,
    chunks: tuple[Chunk, ...],
    roster: str,
) -> tuple[Transcript, TokenUsage]:
    parts: list[tuple[Chunk, Transcript]] = []
    usage = TokenUsage()
    temp_files: list[Path] = []
    try:
        for chunk in chunks:
            if len(chunks) == 1:
                chunk_path = normalized
            else:
                chunk_path = deps.config.workdir / f"{meeting_id}.chunk{chunk.index}.flac"
                await deps.audio.slice(
                    normalized, chunk_path, chunk.start_seconds, chunk.end_seconds
                )
                temp_files.append(chunk_path)
                await deps.bus.publish(
                    meeting_id,
                    progress_event(
                        f"transcribing chunk {chunk.index + 1}/{len(chunks)}",
                        chunk=chunk.index + 1,
                        chunks=len(chunks),
                    ),
                )
            result: TranscriptionResult = await deps.transcriber.transcribe(
                chunk_path, roster=roster, duration_seconds=chunk.duration_seconds
            )
            parts.append((chunk, result.transcript))
            usage = usage + result.usage
    finally:
        for temp in temp_files:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass  # cleanup is best-effort
    transcript = merge_transcripts(parts, overlap_seconds=deps.config.overlap_seconds)
    return transcript, usage


async def process_meeting(deps: PipelineDeps, meeting_id: str) -> None:
    """Run the full pipeline. Never raises: failures are recorded on the
    meeting and published, so the worker loop stays alive."""
    record = await deps.repo.get(meeting_id)
    if record is None:
        await deps.bus.publish(meeting_id, error_event(f"meeting {meeting_id} not found"))
        return
    try:
        state = await _advance(deps, meeting_id, record.state, MeetingState.NORMALIZING)

        started = time.perf_counter()
        normalized = deps.config.workdir / f"{meeting_id}.norm.flac"
        info = await deps.audio.normalize(Path(record.audio_path), normalized)
        await _report_stage(
            deps,
            meeting_id,
            StageReport(
                stage="normalize",
                seconds=time.perf_counter() - started,
                detail=f"16 kHz mono FLAC, {info.duration_seconds:.1f}s",
            ),
        )
        state = await _advance(
            deps,
            meeting_id,
            state,
            MeetingState.TRANSCRIBING,
            duration_seconds=info.duration_seconds,
        )

        started = time.perf_counter()
        silences = await deps.audio.detect_silences(normalized)
        chunks = plan_chunks(
            info.duration_seconds,
            max_chunk_seconds=deps.config.max_chunk_seconds,
            overlap_seconds=deps.config.overlap_seconds,
            silence_points=silences,
        )
        transcript, transcribe_usage = await _transcribe_chunks(
            deps, meeting_id, normalized, chunks, record.roster
        )
        await deps.repo.save_transcript(
            meeting_id, transcript, transcribe_usage, deps.transcriber.model
        )
        await _report_stage(
            deps,
            meeting_id,
            StageReport(
                stage="transcribe",
                seconds=time.perf_counter() - started,
                usage=transcribe_usage,
                model=deps.transcriber.model,
                cost_usd=cost_usd(deps.transcriber.model, transcribe_usage),
                detail=f"{len(chunks)} chunk(s), {len(transcript.utterances)} utterances",
            ),
        )
        state = await _advance(deps, meeting_id, state, MeetingState.SUMMARIZING)

        started = time.perf_counter()
        outcome = await summarize_transcript(
            deps.completer,
            transcript,
            language=record.language,
            roster=record.roster,
            max_repair_attempts=deps.config.max_repair_attempts,
        )
        await deps.repo.save_summary(
            meeting_id, outcome.summary, outcome.usage, outcome.model, outcome.repair_attempts
        )
        await _report_stage(
            deps,
            meeting_id,
            StageReport(
                stage="summarize",
                seconds=time.perf_counter() - started,
                usage=outcome.usage,
                model=outcome.model,
                cost_usd=cost_usd(outcome.model, outcome.usage),
                detail=f"repair_attempts={outcome.repair_attempts}",
            ),
        )
        await _advance(deps, meeting_id, state, MeetingState.COMPLETED)
        await deps.bus.publish(meeting_id, completed_event())
    except Exception as e:  # the pipeline boundary records all failures
        await deps.repo.set_state(meeting_id, MeetingState.FAILED, error=str(e))
        await deps.bus.publish(meeting_id, state_event(MeetingState.FAILED.value))
        await deps.bus.publish(meeting_id, error_event(str(e)))


async def resummarize(
    deps: PipelineDeps, meeting_id: str, *, language: SummaryLanguage
) -> StoredSummary:
    """Re-run pass 2 against the stored transcript. On failure the meeting
    reverts to COMPLETED and keeps its last good summary."""
    record = await deps.repo.get(meeting_id)
    if record is None:
        raise MeetingNotFoundError(f"meeting {meeting_id} not found")
    if record.state is not MeetingState.COMPLETED:
        raise MeetingNotReadyError(
            f"meeting {meeting_id} is {record.state.value}; re-summarize needs a completed meeting"
        )
    transcript = await deps.repo.get_transcript(meeting_id)
    if transcript is None:
        raise MeetingNotReadyError(f"meeting {meeting_id} has no stored transcript")

    state = await _advance(deps, meeting_id, record.state, MeetingState.SUMMARIZING)
    started = time.perf_counter()
    try:
        outcome = await summarize_transcript(
            deps.completer,
            transcript,
            language=language,
            roster=record.roster,
            max_repair_attempts=deps.config.max_repair_attempts,
        )
        stored = await deps.repo.save_summary(
            meeting_id, outcome.summary, outcome.usage, outcome.model, outcome.repair_attempts
        )
        await _report_stage(
            deps,
            meeting_id,
            StageReport(
                stage="summarize",
                seconds=time.perf_counter() - started,
                usage=outcome.usage,
                model=outcome.model,
                cost_usd=cost_usd(outcome.model, outcome.usage),
                detail=f"re-run, language={language.value}, "
                f"repair_attempts={outcome.repair_attempts}",
            ),
        )
        return stored
    finally:
        await _advance(deps, meeting_id, state, MeetingState.COMPLETED)
