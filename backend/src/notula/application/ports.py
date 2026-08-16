"""Ports (protocols) the application layer orchestrates through.

Infrastructure implements these; the application never sees a vendor SDK.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from notula.application.events import PipelineEvent
from notula.domain.models import (
    MeetingSummary,
    StageReport,
    SummaryLanguage,
    TokenUsage,
    Transcript,
)
from notula.domain.state import MeetingState


@dataclass(frozen=True, slots=True)
class AudioInfo:
    duration_seconds: float
    size_bytes: int


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    transcript: Transcript
    usage: TokenUsage
    model: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    usage: TokenUsage
    model: str


@dataclass(slots=True)
class MeetingRecord:
    id: str
    filename: str
    state: MeetingState
    language: SummaryLanguage
    roster: str
    audio_path: str
    created_at: datetime
    duration_seconds: float | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class StoredSummary:
    summary: MeetingSummary
    model: str
    usage: TokenUsage
    repair_attempts: int
    version: int
    created_at: datetime


class AudioProcessor(Protocol):
    async def probe(self, path: Path) -> AudioInfo: ...

    async def normalize(self, src: Path, dst: Path) -> AudioInfo:
        """Convert to the pipeline-standard format (16 kHz mono FLAC)."""
        ...

    async def detect_silences(self, path: Path) -> tuple[float, ...]:
        """Midpoints (seconds) of detected silences, for chunk-boundary snapping."""
        ...

    async def slice(
        self, src: Path, dst: Path, start_seconds: float, end_seconds: float
    ) -> None: ...


class Transcriber(Protocol):
    @property
    def model(self) -> str: ...

    async def transcribe(
        self, path: Path, *, roster: str, duration_seconds: float
    ) -> TranscriptionResult: ...


class ChatCompleter(Protocol):
    """Pass-2 LLM. Returns raw text: the repair loop owns validation."""

    @property
    def model(self) -> str: ...

    async def complete_json(self, system: str, user: str) -> Completion: ...


class MeetingRepository(Protocol):
    async def add(self, meeting: MeetingRecord) -> None: ...

    async def get(self, meeting_id: str) -> MeetingRecord | None: ...

    async def list_recent(self, limit: int = 50) -> Sequence[MeetingRecord]: ...

    async def list_in_states(self, states: frozenset[MeetingState]) -> Sequence[MeetingRecord]: ...

    async def set_state(
        self,
        meeting_id: str,
        state: MeetingState,
        *,
        error: str | None = None,
        duration_seconds: float | None = None,
    ) -> None: ...

    async def save_transcript(
        self, meeting_id: str, transcript: Transcript, usage: TokenUsage, model: str
    ) -> None: ...

    async def get_transcript(self, meeting_id: str) -> Transcript | None: ...

    async def save_summary(
        self,
        meeting_id: str,
        summary: MeetingSummary,
        usage: TokenUsage,
        model: str,
        repair_attempts: int,
    ) -> StoredSummary: ...

    async def get_latest_summary(self, meeting_id: str) -> StoredSummary | None: ...

    async def list_summaries(self, meeting_id: str) -> Sequence[StoredSummary]: ...

    async def add_stage_report(self, meeting_id: str, report: StageReport) -> None: ...

    async def get_stage_reports(self, meeting_id: str) -> Sequence[StageReport]: ...


class EventBus(Protocol):
    async def publish(self, meeting_id: str, event: PipelineEvent) -> None: ...

    def subscribe(self, meeting_id: str) -> AsyncIterator[PipelineEvent]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    workdir: Path
    max_chunk_seconds: float = 20 * 60.0
    overlap_seconds: float = 15.0
    max_repair_attempts: int = 2


@dataclass(frozen=True, slots=True)
class PipelineDeps:
    repo: MeetingRepository
    bus: EventBus
    audio: AudioProcessor
    transcriber: Transcriber
    completer: ChatCompleter
    clock: Clock
    config: PipelineConfig
