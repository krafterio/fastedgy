# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime, timedelta, timezone

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.test.models.queued_task import QueuedTask


# --- state helpers ----------------------------------------------------------


async def test_mark_as_done_sets_state_and_date(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func")
    task.mark_as_done()

    assert task.state == QueuedTaskState.done
    assert task.date_done is not None
    assert task.is_finished is True


async def test_mark_as_doing_clears_terminal_dates(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func")
    task.mark_as_done()
    task.mark_as_doing()

    assert task.state == QueuedTaskState.doing
    assert task.date_started is not None
    assert task.date_done is None
    assert task.is_active is True


async def test_mark_as_failed_captures_exception(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func")
    task.mark_as_failed(exception_name="ValueError", exception_message="boom")

    assert task.state == QueuedTaskState.failed
    assert task.exception_name == "ValueError"
    assert task.exception_message == "boom"
    assert task.can_be_restarted is True


async def test_mark_as_cancelled_and_stopped(setup_db: FastEdgy) -> None:
    cancelled = QueuedTask(module_name="module", function_name="func")
    cancelled.mark_as_cancelled()

    stopped = QueuedTask(module_name="module", function_name="func")
    stopped.mark_as_stopped()

    assert cancelled.state == QueuedTaskState.cancelled
    assert cancelled.date_cancelled is not None
    assert stopped.state == QueuedTaskState.stopped
    assert stopped.can_be_restarted is True


async def test_restart_resets_execution_fields(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func")
    task.retry_count = 3
    task.mark_as_failed(exception_name="ValueError")
    task.restart()

    assert task.state == QueuedTaskState.enqueued
    assert task.retry_count == 0
    assert task.exception_name is None
    assert task.date_failed is None


async def test_can_be_cancelled_only_for_active_states(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func", state=QueuedTaskState.enqueued)

    assert task.can_be_cancelled is True

    task.mark_as_done()

    assert task.can_be_cancelled is False


# --- auto-save computations -------------------------------------------------


async def test_save_auto_generates_name_from_module_and_function(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func", state=QueuedTaskState.enqueued)
    await task.save()

    assert task.name == "module.func"
    assert task.date_enqueued is not None


async def test_save_name_falls_back_for_serialized_function(setup_db: FastEdgy) -> None:
    task = QueuedTask(serialized_function=b"blob", state=QueuedTaskState.enqueued)
    await task.save()

    assert task.name == "local_function"


async def test_save_computes_execution_time(setup_db: FastEdgy) -> None:
    task = QueuedTask(module_name="module", function_name="func", state=QueuedTaskState.enqueued)
    task.date_started = datetime.now(timezone.utc) - timedelta(seconds=5)
    task.mark_as_done()
    await task.save()

    assert task.date_ended == task.date_done
    assert 4 <= task.execution_time <= 8


async def test_drain_pending_db_logs_waits_then_cancels(setup_db) -> None:
    import asyncio

    from fastedgy.queued_task.logging import QueuedTaskLogger

    done: list[str] = []

    async def short() -> None:
        await asyncio.sleep(0.05)
        done.append("short")

    async def hung() -> None:
        await asyncio.sleep(3600)

    short_task = asyncio.get_running_loop().create_task(short())
    hung_task = asyncio.get_running_loop().create_task(hung())
    QueuedTaskLogger._pending_db_logs.add(short_task)
    QueuedTaskLogger._pending_db_logs.add(hung_task)
    short_task.add_done_callback(QueuedTaskLogger._pending_db_logs.discard)
    hung_task.add_done_callback(QueuedTaskLogger._pending_db_logs.discard)

    await QueuedTaskLogger.drain_pending_db_logs(timeout=0.5)

    assert done == ["short"]
    assert hung_task.cancelled()
