"""Pydantic response/request models — the only place API JSON shapes are defined."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from notula.application.ports import MeetingRecord, StoredSummary
from notula.domain.models import MeetingSummary, StageReport, Transcript


class MeetingOut(BaseModel):
    id: str
    filename: str
    state: str
    language: str
    duration_seconds: float | None
    created_at: str
    error: str | None

    @classmethod
    def from_record(cls, record: MeetingRecord) -> MeetingOut:
        return cls(
            id=record.id,
            filename=record.filename,
            state=record.state.value,
            language=record.language.value,
            duration_seconds=record.duration_seconds,
            created_at=record.created_at.isoformat(),
            error=record.error,
        )


class StageOut(BaseModel):
    stage: str
    seconds: float
    model: str
    cost_usd: float | None
    input_tokens: int
    output_tokens: int
    detail: str

    @classmethod
    def from_report(cls, report: StageReport) -> StageOut:
        return cls(
            stage=report.stage,
            seconds=report.seconds,
            model=report.model,
            cost_usd=report.cost_usd,
            input_tokens=report.usage.input_tokens,
            output_tokens=report.usage.output_tokens,
            detail=report.detail,
        )


class ActionItemOut(BaseModel):
    task: str
    owner: str | None
    due: str | None


class SummaryOut(BaseModel):
    title: str
    tldr: str
    key_points: list[str]
    decisions: list[str]
    action_items: list[ActionItemOut]
    open_questions: list[str]
    language: str
    model: str
    version: int
    repair_attempts: int
    created_at: str

    @classmethod
    def from_stored(cls, stored: StoredSummary) -> SummaryOut:
        summary: MeetingSummary = stored.summary
        return cls(
            title=summary.title,
            tldr=summary.tldr,
            key_points=list(summary.key_points),
            decisions=list(summary.decisions),
            action_items=[
                ActionItemOut(task=a.task, owner=a.owner, due=a.due) for a in summary.action_items
            ],
            open_questions=list(summary.open_questions),
            language=summary.language.value,
            model=stored.model,
            version=stored.version,
            repair_attempts=stored.repair_attempts,
            created_at=stored.created_at.isoformat(),
        )


class UtteranceOut(BaseModel):
    start: float
    speaker: str
    text: str


class TranscriptOut(BaseModel):
    duration_seconds: float
    utterances: list[UtteranceOut]

    @classmethod
    def from_transcript(cls, transcript: Transcript) -> TranscriptOut:
        return cls(
            duration_seconds=transcript.duration_seconds,
            utterances=[
                UtteranceOut(start=u.start_seconds, speaker=u.speaker, text=u.text)
                for u in transcript.utterances
            ],
        )


class MeetingDetailOut(BaseModel):
    meeting: MeetingOut
    stages: list[StageOut]
    summary: SummaryOut | None
    transcript: TranscriptOut | None


class MeetingListOut(BaseModel):
    meetings: list[MeetingOut]


class SubmitOut(BaseModel):
    id: str


class ResummarizeIn(BaseModel):
    language: Literal["en", "id"]


class HealthOut(BaseModel):
    status: str
    provider: str
