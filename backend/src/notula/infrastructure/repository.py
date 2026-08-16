"""SQLAlchemy implementation of the MeetingRepository port."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notula.application.ports import Clock, MeetingRecord, StoredSummary
from notula.domain.models import (
    MeetingSummary,
    StageReport,
    SummaryLanguage,
    TokenUsage,
    Transcript,
)
from notula.domain.parsing import (
    summary_from_dict,
    summary_to_dict,
    transcript_from_dict,
    transcript_to_dict,
)
from notula.domain.state import MeetingState
from notula.infrastructure.db import MeetingRow, StageReportRow, SummaryRow, TranscriptRow


def _to_record(row: MeetingRow) -> MeetingRecord:
    return MeetingRecord(
        id=row.id,
        filename=row.filename,
        state=MeetingState(row.state),
        language=SummaryLanguage(row.language),
        roster=row.roster,
        audio_path=row.audio_path,
        created_at=datetime.fromisoformat(row.created_at),
        duration_seconds=row.duration_seconds,
        error=row.error,
    )


def _to_stored_summary(row: SummaryRow) -> StoredSummary:
    payload: dict[str, object] = json.loads(row.payload)
    return StoredSummary(
        summary=summary_from_dict(payload),
        model=row.model,
        usage=TokenUsage(row.input_tokens, row.output_tokens),
        repair_attempts=row.repair_attempts,
        version=row.version,
        created_at=datetime.fromisoformat(row.created_at),
    )


class SqlAlchemyMeetingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._sessions = session_factory
        self._clock = clock

    async def add(self, meeting: MeetingRecord) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                MeetingRow(
                    id=meeting.id,
                    filename=meeting.filename,
                    state=meeting.state.value,
                    language=meeting.language.value,
                    roster=meeting.roster,
                    audio_path=meeting.audio_path,
                    created_at=meeting.created_at.isoformat(),
                    duration_seconds=meeting.duration_seconds,
                    error=meeting.error,
                )
            )

    async def get(self, meeting_id: str) -> MeetingRecord | None:
        async with self._sessions() as session:
            row = await session.get(MeetingRow, meeting_id)
            return None if row is None else _to_record(row)

    async def list_recent(self, limit: int = 50) -> Sequence[MeetingRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(MeetingRow).order_by(MeetingRow.created_at.desc()).limit(limit)
            )
            return [_to_record(row) for row in rows]

    async def list_in_states(self, states: frozenset[MeetingState]) -> Sequence[MeetingRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(MeetingRow).where(MeetingRow.state.in_([s.value for s in states]))
            )
            return [_to_record(row) for row in rows]

    async def set_state(
        self,
        meeting_id: str,
        state: MeetingState,
        *,
        error: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        values: dict[str, object] = {"state": state.value, "error": error}
        if duration_seconds is not None:
            values["duration_seconds"] = duration_seconds
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(MeetingRow).where(MeetingRow.id == meeting_id).values(**values)
            )

    async def save_transcript(
        self, meeting_id: str, transcript: Transcript, usage: TokenUsage, model: str
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.merge(
                TranscriptRow(
                    meeting_id=meeting_id,
                    payload=json.dumps(transcript_to_dict(transcript), ensure_ascii=False),
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    model=model,
                )
            )

    async def get_transcript(self, meeting_id: str) -> Transcript | None:
        async with self._sessions() as session:
            row = await session.get(TranscriptRow, meeting_id)
            if row is None:
                return None
            payload: dict[str, object] = json.loads(row.payload)
            duration = float(payload.get("duration_seconds", 0.0))  # type: ignore[arg-type]
            return transcript_from_dict(payload, duration_seconds=duration)

    async def save_summary(
        self,
        meeting_id: str,
        summary: MeetingSummary,
        usage: TokenUsage,
        model: str,
        repair_attempts: int,
    ) -> StoredSummary:
        created_at = self._clock.now()
        async with self._sessions() as session, session.begin():
            current = await session.scalar(
                select(func.max(SummaryRow.version)).where(SummaryRow.meeting_id == meeting_id)
            )
            version = (current or 0) + 1
            session.add(
                SummaryRow(
                    meeting_id=meeting_id,
                    version=version,
                    payload=json.dumps(summary_to_dict(summary), ensure_ascii=False),
                    model=model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    repair_attempts=repair_attempts,
                    created_at=created_at.isoformat(),
                )
            )
        return StoredSummary(
            summary=summary,
            model=model,
            usage=usage,
            repair_attempts=repair_attempts,
            version=version,
            created_at=created_at,
        )

    async def get_latest_summary(self, meeting_id: str) -> StoredSummary | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(SummaryRow)
                .where(SummaryRow.meeting_id == meeting_id)
                .order_by(SummaryRow.version.desc())
                .limit(1)
            )
            return None if row is None else _to_stored_summary(row)

    async def list_summaries(self, meeting_id: str) -> Sequence[StoredSummary]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(SummaryRow)
                .where(SummaryRow.meeting_id == meeting_id)
                .order_by(SummaryRow.version.asc())
            )
            return [_to_stored_summary(row) for row in rows]

    async def add_stage_report(self, meeting_id: str, report: StageReport) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                StageReportRow(
                    meeting_id=meeting_id,
                    stage=report.stage,
                    seconds=report.seconds,
                    input_tokens=report.usage.input_tokens,
                    output_tokens=report.usage.output_tokens,
                    model=report.model,
                    cost_usd=report.cost_usd,
                    detail=report.detail,
                    created_at=self._clock.now().isoformat(),
                )
            )

    async def get_stage_reports(self, meeting_id: str) -> Sequence[StageReport]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(StageReportRow)
                .where(StageReportRow.meeting_id == meeting_id)
                .order_by(StageReportRow.id.asc())
            )
            return [
                StageReport(
                    stage=row.stage,
                    seconds=row.seconds,
                    usage=TokenUsage(row.input_tokens, row.output_tokens),
                    model=row.model,
                    cost_usd=row.cost_usd,
                    detail=row.detail,
                )
                for row in rows
            ]
