from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from notula.application.ports import MeetingRecord
from notula.domain.models import (
    ActionItem,
    MeetingSummary,
    StageReport,
    SummaryLanguage,
    TokenUsage,
    Transcript,
    Utterance,
)
from notula.domain.state import MeetingState
from notula.infrastructure.db import init_db, make_engine, make_session_factory
from notula.infrastructure.repository import SqlAlchemyMeetingRepository

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[SqlAlchemyMeetingRepository]:
    engine = make_engine(tmp_path / "test.db")
    await init_db(engine)
    yield SqlAlchemyMeetingRepository(make_session_factory(engine), FixedClock())
    await engine.dispose()


def _record(meeting_id: str = "m1") -> MeetingRecord:
    return MeetingRecord(
        id=meeting_id,
        filename="standup.wav",
        state=MeetingState.UPLOADED,
        language=SummaryLanguage.ENGLISH,
        roster="Rina, Dimas",
        audio_path=f"/tmp/{meeting_id}.wav",  # noqa: S108 - test value only
        created_at=NOW,
    )


_TRANSCRIPT = Transcript(
    utterances=(
        Utterance(1.0, "Rina", "Selamat pagi semua."),
        Utterance(6.5, "Speaker 2", "Morning — quick update from me."),
    ),
    duration_seconds=42.5,
)

_SUMMARY = MeetingSummary(
    title="Weekly sync",
    tldr="Short sync about the release.",
    key_points=("Release moved",),
    decisions=("We agreed to move the release.",),
    action_items=(ActionItem(task="Update checklist", owner="Rina", due=None),),
    open_questions=(),
    language=SummaryLanguage.ENGLISH,
)


async def test_add_get_roundtrip(repo: SqlAlchemyMeetingRepository) -> None:
    await repo.add(_record())
    fetched = await repo.get("m1")
    assert fetched is not None
    assert fetched.filename == "standup.wav"
    assert fetched.state is MeetingState.UPLOADED
    assert fetched.language is SummaryLanguage.ENGLISH
    assert fetched.created_at == NOW
    assert fetched.duration_seconds is None
    assert fetched.error is None


async def test_get_missing_returns_none(repo: SqlAlchemyMeetingRepository) -> None:
    assert await repo.get("nope") is None


async def test_list_recent_and_states(repo: SqlAlchemyMeetingRepository) -> None:
    await repo.add(_record("m1"))
    await repo.add(_record("m2"))
    await repo.set_state("m2", MeetingState.NORMALIZING)
    assert {m.id for m in await repo.list_recent()} == {"m1", "m2"}
    active = await repo.list_in_states(frozenset({MeetingState.NORMALIZING}))
    assert [m.id for m in active] == ["m2"]


async def test_set_state_with_error_and_duration(repo: SqlAlchemyMeetingRepository) -> None:
    await repo.add(_record())
    await repo.set_state("m1", MeetingState.FAILED, error="boom", duration_seconds=12.5)
    fetched = await repo.get("m1")
    assert fetched is not None
    assert fetched.state is MeetingState.FAILED
    assert fetched.error == "boom"
    assert fetched.duration_seconds == 12.5
    # A later transition without error clears it and keeps the duration.
    await repo.set_state("m1", MeetingState.NORMALIZING)
    fetched = await repo.get("m1")
    assert fetched is not None
    assert fetched.error is None
    assert fetched.duration_seconds == 12.5


async def test_transcript_roundtrip(repo: SqlAlchemyMeetingRepository) -> None:
    await repo.add(_record())
    assert await repo.get_transcript("m1") is None
    await repo.save_transcript("m1", _TRANSCRIPT, TokenUsage(100, 50), "mock")
    loaded = await repo.get_transcript("m1")
    assert loaded == _TRANSCRIPT


async def test_summary_versions(repo: SqlAlchemyMeetingRepository) -> None:
    await repo.add(_record())
    assert await repo.get_latest_summary("m1") is None
    first = await repo.save_summary("m1", _SUMMARY, TokenUsage(10, 5), "mock", 0)
    second = await repo.save_summary("m1", _SUMMARY, TokenUsage(12, 6), "mock", 1)
    assert (first.version, second.version) == (1, 2)
    latest = await repo.get_latest_summary("m1")
    assert latest is not None
    assert latest.version == 2
    assert latest.repair_attempts == 1
    assert latest.summary == _SUMMARY
    assert latest.created_at == NOW
    assert [s.version for s in await repo.list_summaries("m1")] == [1, 2]


async def test_stage_reports_roundtrip(repo: SqlAlchemyMeetingRepository) -> None:
    await repo.add(_record())
    await repo.add_stage_report(
        "m1", StageReport("transcribe", 1.5, TokenUsage(2000, 300), "mock", 0.0, "2 chunks")
    )
    await repo.add_stage_report(
        "m1", StageReport("summarize", 0.4, TokenUsage(900, 200), "unknown-model", None, "")
    )
    reports = await repo.get_stage_reports("m1")
    assert [r.stage for r in reports] == ["transcribe", "summarize"]
    assert reports[0].usage == TokenUsage(2000, 300)
    assert reports[0].cost_usd == 0.0
    assert reports[1].cost_usd is None
