import asyncio

from notula.application.events import PipelineEvent, state_event
from notula.infrastructure.events import InMemoryEventBus


async def test_publish_reaches_all_subscribers() -> None:
    bus = InMemoryEventBus()
    first = bus.subscribe("m1")
    second = bus.subscribe("m1")
    await bus.publish("m1", state_event("normalizing"))
    got_first = await asyncio.wait_for(anext(first), timeout=1)
    got_second = await asyncio.wait_for(anext(second), timeout=1)
    assert got_first == got_second == state_event("normalizing")


async def test_registration_is_eager() -> None:
    bus = InMemoryEventBus()
    stream = bus.subscribe("m1")
    # Published before the first __anext__ — must still be delivered.
    await bus.publish("m1", state_event("transcribing"))
    assert await asyncio.wait_for(anext(stream), timeout=1) == state_event("transcribing")


async def test_subscriber_removed_on_close() -> None:
    bus = InMemoryEventBus()
    stream = bus.subscribe("m1")
    await bus.publish("m1", state_event("normalizing"))
    await anext(stream)
    await stream.aclose()  # type: ignore[attr-defined]
    assert bus._subscribers == {}


async def test_publish_without_subscribers_is_noop() -> None:
    bus = InMemoryEventBus()
    await bus.publish("m1", PipelineEvent("progress", {"message": "hi"}))


async def test_events_are_scoped_per_meeting() -> None:
    bus = InMemoryEventBus()
    m1 = bus.subscribe("m1")
    await bus.publish("m2", state_event("normalizing"))
    await bus.publish("m1", state_event("summarizing"))
    assert await asyncio.wait_for(anext(m1), timeout=1) == state_event("summarizing")
