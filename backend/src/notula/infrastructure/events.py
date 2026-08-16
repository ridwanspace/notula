"""In-memory pub/sub for pipeline progress (fanned out to SSE clients).

Events are ephemeral by design: durable progress lives in the meeting record
and stage reports, so a reconnecting client re-reads state and misses nothing
that matters.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from notula.application.events import PipelineEvent


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[PipelineEvent]]] = {}

    async def publish(self, meeting_id: str, event: PipelineEvent) -> None:
        for queue in list(self._subscribers.get(meeting_id, [])):
            queue.put_nowait(event)

    def subscribe(self, meeting_id: str) -> AsyncIterator[PipelineEvent]:
        # Register eagerly (not on first __anext__) so no event published between
        # subscribe() and the first read is lost.
        queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        self._subscribers.setdefault(meeting_id, []).append(queue)

        async def _stream() -> AsyncIterator[PipelineEvent]:
            try:
                while True:
                    yield await queue.get()
            finally:
                subscribers = self._subscribers.get(meeting_id, [])
                if queue in subscribers:
                    subscribers.remove(queue)
                if not subscribers:
                    self._subscribers.pop(meeting_id, None)

        return _stream()
