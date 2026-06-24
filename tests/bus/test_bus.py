# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.bus import BaseEvent, Bus


class SampleEvent(BaseEvent):
    def __init__(self, value: Any) -> None:
        self.value = value


async def test_dispatch_calls_registered_handler() -> None:
    bus = Bus()
    seen: list[Any] = []

    async def handler(event: SampleEvent) -> None:
        seen.append(event.value)

    bus.register(SampleEvent, handler)
    await bus.dispatch(SampleEvent(42))

    assert seen == [42]


async def test_handlers_run_in_priority_order() -> None:
    bus = Bus()
    order: list[str] = []

    def low(event: SampleEvent) -> None:
        order.append("low")

    def high(event: SampleEvent) -> None:
        order.append("high")

    bus.register(SampleEvent, low, priority=200)
    bus.register(SampleEvent, high, priority=10)
    await bus.dispatch(SampleEvent(1))

    assert order == ["high", "low"]


async def test_sync_and_async_handlers_both_run() -> None:
    bus = Bus()
    seen: list[str] = []

    def sync_handler(event: SampleEvent) -> None:
        seen.append("sync")

    async def async_handler(event: SampleEvent) -> None:
        seen.append("async")

    bus.register(SampleEvent, sync_handler)
    bus.register(SampleEvent, async_handler)
    await bus.dispatch(SampleEvent(1))

    assert set(seen) == {"sync", "async"}


async def test_unregister_removes_a_handler() -> None:
    bus = Bus()
    seen: list[int] = []

    def handler(event: SampleEvent) -> None:
        seen.append(1)

    bus.register(SampleEvent, handler)
    bus.unregister(SampleEvent, handler)
    await bus.dispatch(SampleEvent(1))

    assert seen == []


async def test_has_listeners_and_clear() -> None:
    bus = Bus()

    def handler(event: SampleEvent) -> None: ...

    bus.register(SampleEvent, handler)
    assert bus.has_listeners(SampleEvent) is True

    bus.clear(SampleEvent)
    assert bus.has_listeners(SampleEvent) is False
