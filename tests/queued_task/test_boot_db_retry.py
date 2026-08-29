# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

import pytest

from fastedgy.queued_task.services.queue_worker_manager import QueueWorkerManager


class _Stub:
    def __init__(self, failures: int, error: Exception) -> None:
        self.calls = 0
        self.touches = 0
        self._failures = failures
        self._error = error

    def _touch_health_file(self) -> None:
        self.touches += 1

    async def _init_db(self) -> None:
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error


async def _unreachable_database() -> Exception:
    """The real failure of a deploy window: the db name no longer resolves.

    Raised through asyncpg itself, since the classifier decides on the driver
    frames in the traceback, not on the exception type alone.
    """
    import asyncpg

    try:
        await asyncpg.connect("postgresql://user:pwd@db.invalid:5432/db", timeout=2)
    except Exception as e:
        return e

    raise AssertionError("db.invalid resolved")  # pragma: no cover


async def test_init_db_retries_while_the_database_is_unreachable(monkeypatch) -> None:
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _delay: real_sleep(0))
    stub = _Stub(failures=2, error=await _unreachable_database())

    await QueueWorkerManager._init_db_with_retry(stub)  # type: ignore[arg-type]

    assert stub.calls == 3
    assert stub.touches == 3


async def test_init_db_aborts_immediately_on_a_non_outage_error(monkeypatch) -> None:
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _delay: real_sleep(0))
    stub = _Stub(failures=1, error=ValueError("bad trigger sql"))

    with pytest.raises(ValueError):
        await QueueWorkerManager._init_db_with_retry(stub)  # type: ignore[arg-type]

    assert stub.calls == 1


async def test_init_db_gives_up_once_the_budget_is_spent(monkeypatch) -> None:
    from fastedgy.queued_task.services import queue_worker_manager as module

    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _delay: real_sleep(0))
    monkeypatch.setattr(module, "BOOT_DB_RETRY_BUDGET", 0.0)
    stub = _Stub(failures=99, error=await _unreachable_database())

    with pytest.raises(OSError):
        await QueueWorkerManager._init_db_with_retry(stub)  # type: ignore[arg-type]

    assert stub.calls == 1
