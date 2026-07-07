# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest
from sqlalchemy.exc import SQLAlchemyError

from fastedgy.bus import BaseEvent
from fastedgy.bus.service import Bus


class _Event(BaseEvent):
    pass


class _CriticalError(Exception):
    pass


async def test_registered_critical_exception_propagates() -> None:
    Bus.register_critical_exception(_CriticalError)
    try:
        bus = Bus()

        async def failing_handler(event: _Event) -> None:
            raise _CriticalError("ambient state doomed")

        bus.register(_Event, failing_handler)

        with pytest.raises(_CriticalError):
            await bus.dispatch(_Event())
    finally:
        Bus.critical_exceptions = tuple(e for e in Bus.critical_exceptions if e is not _CriticalError)


async def test_orm_import_registers_sqlalchemy_errors_as_critical() -> None:
    import fastedgy.orm  # noqa: F401  (wires SQLAlchemyError on import)

    bus = Bus()

    async def failing_handler(event: _Event) -> None:
        raise SQLAlchemyError("update households failed")

    bus.register(_Event, failing_handler)

    with pytest.raises(SQLAlchemyError):
        await bus.dispatch(_Event())


async def test_non_critical_error_in_handler_is_isolated() -> None:
    bus = Bus()
    calls: list[str] = []

    async def broken_handler(event: _Event) -> None:
        raise RuntimeError("handler bug")

    async def next_handler(event: _Event) -> None:
        calls.append("ran")

    bus.register(_Event, broken_handler, priority=10)
    bus.register(_Event, next_handler, priority=20)

    await bus.dispatch(_Event())

    assert calls == ["ran"]
