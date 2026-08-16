import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from notula.application.ports import MeetingRecord, MeetingRepository
from notula.domain.models import SummaryLanguage
from notula.domain.state import MeetingState
from notula.infrastructure.worker import MeetingWorker


def _record(meeting_id: str, state: MeetingState) -> MeetingRecord:
    return MeetingRecord(
        id=meeting_id,
        filename="a.wav",
        state=state,
        language=SummaryLanguage.ENGLISH,
        roster="",
        audio_path="a.wav",
        created_at=datetime(2026, 8, 16, tzinfo=UTC),
    )


class FakeRepo:
    """Only the slice of the repository the worker touches."""

    def __init__(self, records: list[MeetingRecord]) -> None:
        self._records = records

    async def list_in_states(self, states: frozenset[MeetingState]) -> Sequence[MeetingRecord]:
        return [r for r in self._records if r.state in states]


def _repo(records: list[MeetingRecord]) -> MeetingRepository:
    return cast(MeetingRepository, FakeRepo(records))


async def test_enqueue_processes_meeting() -> None:
    processed: list[str] = []

    async def process(meeting_id: str) -> None:
        processed.append(meeting_id)

    worker = MeetingWorker(process, _repo([]))
    await worker.start()
    worker.enqueue("m1")
    worker.enqueue("m2")
    await asyncio.wait_for(worker.drain(), timeout=2)
    await worker.stop()
    assert processed == ["m1", "m2"]


async def test_recover_enqueues_only_active_states() -> None:
    processed: list[str] = []

    async def process(meeting_id: str) -> None:
        processed.append(meeting_id)

    records = [
        _record("m1", MeetingState.TRANSCRIBING),
        _record("m2", MeetingState.COMPLETED),
        _record("m3", MeetingState.UPLOADED),
        _record("m4", MeetingState.FAILED),
    ]
    worker = MeetingWorker(process, _repo(records))
    recovered = await worker.recover()
    assert set(recovered) == {"m1", "m3"}
    await worker.start()
    await asyncio.wait_for(worker.drain(), timeout=2)
    await worker.stop()
    assert set(processed) == {"m1", "m3"}


async def test_process_error_does_not_kill_consumer() -> None:
    processed: list[str] = []

    async def process(meeting_id: str) -> None:
        if meeting_id == "boom":
            raise RuntimeError("unexpected")
        processed.append(meeting_id)

    worker = MeetingWorker(process, _repo([]))
    await worker.start()
    worker.enqueue("boom")
    worker.enqueue("after")
    await asyncio.wait_for(worker.drain(), timeout=2)
    await worker.stop()
    assert processed == ["after"]


async def test_stop_is_idempotent_and_start_once() -> None:
    async def process(meeting_id: str) -> None:  # pragma: no cover - never called
        raise AssertionError

    worker = MeetingWorker(process, _repo([]))
    await worker.start()
    await worker.start()  # second start must not spawn a second consumer
    await worker.stop()
    await worker.stop()
