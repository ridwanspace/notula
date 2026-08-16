"""Single-consumer asyncio worker with restart recovery.

Deliberately not Redis/arq: a portfolio pipeline that must run from a fresh
clone favors zero infrastructure, and interrupted meetings are recovered from
the persisted state machine on startup instead of from a durable queue
(ADR-0002).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from notula.application.ports import MeetingRepository
from notula.domain.state import ACTIVE_STATES

logger = structlog.get_logger(__name__)


class MeetingWorker:
    def __init__(self, process: Callable[[str], Awaitable[None]], repo: MeetingRepository) -> None:
        self._process = process
        self._repo = repo
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def enqueue(self, meeting_id: str) -> None:
        self._queue.put_nowait(meeting_id)

    async def recover(self) -> list[str]:
        """Re-enqueue meetings left in a non-terminal state by a previous run."""
        interrupted = await self._repo.list_in_states(ACTIVE_STATES)
        ids = [meeting.id for meeting in interrupted]
        for meeting_id in ids:
            self.enqueue(meeting_id)
        return ids

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def drain(self) -> None:
        """Wait until every enqueued meeting has been processed."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            meeting_id = await self._queue.get()
            try:
                # process_meeting records its own failures in the state machine;
                # this guard only keeps the consumer alive if something escapes.
                await self._process(meeting_id)
            except Exception:
                logger.exception("worker.process_failed", meeting_id=meeting_id)
            finally:
                self._queue.task_done()
