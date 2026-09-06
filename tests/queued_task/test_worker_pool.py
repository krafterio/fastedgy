# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
from typing import Any

import pytest

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.services.queue_worker_manager import QueueWorkerManager
from fastedgy.queued_task.services.worker_pool import (
    BOOT_GRACE,
    IDLE_WEDGE_TIMEOUT,
    WorkerPool,
    WorkerProcess,
    WorkerSlot,
)
from fastedgy.queued_task.services.worker_process import (
    MSG_RESULT,
    MSG_STARTED,
    MSG_SYNC_FINISHED,
    STATUS_WORKER_DIED,
)

from .helpers import queue


class FakeProcess:
    def __init__(self) -> None:
        self.pid = None
        self.exitcode = 1

    def join(self, timeout: float | None = None) -> None:
        pass


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.closed = False

    def send(self, message: Any) -> None:
        self.sent.append(message)

    def fileno(self) -> int:
        raise OSError("no fd")

    def close(self) -> None:
        self.closed = True


def build_pool(workers_count: int = 2, concurrency: int = 2) -> tuple[WorkerPool, list[WorkerProcess]]:
    pool = WorkerPool(workers=workers_count, concurrency=concurrency)
    workers = []

    for index in range(workers_count):
        conn = FakeConnection()
        worker = WorkerProcess(index, FakeProcess(), conn, asyncio.get_event_loop().time())  # type: ignore[arg-type]
        worker.last_beat = asyncio.get_event_loop().time()
        pool._workers[index] = worker
        workers.append(worker)

    return pool, workers


async def dispatch(pool: WorkerPool, slot: WorkerSlot, task: Any) -> asyncio.Task[dict[str, Any]]:
    job = asyncio.create_task(slot.run_task(task))
    await asyncio.sleep(0)

    return job


async def test_pool_hands_out_at_most_workers_times_concurrency_slots(setup_db: FastEdgy) -> None:
    pool, _ = build_pool(workers_count=1, concurrency=2)

    assert await pool.get_available_worker() is not None
    assert await pool.get_available_worker() is not None
    assert await pool.get_available_worker() is None


async def test_pool_recycles_a_returned_slot(setup_db: FastEdgy) -> None:
    pool, _ = build_pool(workers_count=1, concurrency=1)
    slot = await pool.get_available_worker()

    assert slot is not None

    await pool.return_worker(slot)

    assert await pool.get_available_worker() is slot


async def test_pool_refuses_slots_without_a_live_worker(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    workers[0].alive = False

    assert await pool.get_available_worker() is None


async def test_dispatch_picks_the_least_loaded_worker(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=2, concurrency=2)
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")

    first = await pool.get_available_worker()
    second = await pool.get_available_worker()

    assert first is not None
    assert second is not None

    await dispatch(pool, first, task)
    await dispatch(pool, second, task)

    assert len(workers[0].runs) == 1
    assert len(workers[1].runs) == 1


async def test_worker_death_reports_a_run_that_never_started(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
    slot = await pool.get_available_worker()

    assert slot is not None

    job = await dispatch(pool, slot, task)
    pool._shutting_down = True
    pool._on_process_death(workers[0])
    result = await job

    assert result["status"] == STATUS_WORKER_DIED
    assert result["started"] is False


async def test_worker_death_reports_a_run_that_started(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
    slot = await pool.get_available_worker()

    assert slot is not None

    job = await dispatch(pool, slot, task)
    run_id = next(iter(workers[0].runs))
    pool._handle(workers[0], (MSG_STARTED, run_id))
    pool._shutting_down = True
    pool._on_process_death(workers[0])
    result = await job

    assert result["status"] == STATUS_WORKER_DIED
    assert result["started"] is True


async def test_result_carries_back_to_the_waiting_slot(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
    slot = await pool.get_available_worker()

    assert slot is not None

    job = await dispatch(pool, slot, task)
    run_id = next(iter(workers[0].runs))
    pool._handle(workers[0], (MSG_RESULT, run_id, {"status": "success"}))

    assert (await job)["status"] == "success"


async def test_a_zombie_sync_thread_keeps_its_run_registered(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
    slot = await pool.get_available_worker()

    assert slot is not None

    job = await dispatch(pool, slot, task)
    run_id = next(iter(workers[0].runs))
    pool._handle(workers[0], (MSG_RESULT, run_id, {"status": "failed", "pending_sync": True}))
    await job

    assert slot.pending_sync_finished is not None
    assert not slot.pending_sync_finished.is_set()
    assert run_id not in workers[0].runs

    pool._handle(workers[0], (MSG_SYNC_FINISHED, run_id))

    assert slot.pending_sync_finished.is_set()


async def test_worker_death_releases_a_zombie_sync_thread(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
    slot = await pool.get_available_worker()

    assert slot is not None

    job = await dispatch(pool, slot, task)
    run_id = next(iter(workers[0].runs))
    pool._handle(workers[0], (MSG_RESULT, run_id, {"status": "failed", "pending_sync": True}))
    await job

    pool._shutting_down = True
    pool._on_process_death(workers[0])

    assert slot.pending_sync_finished is not None
    assert slot.pending_sync_finished.is_set()


async def _doing_task(**kwargs: Any) -> Any:
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers", **kwargs)
    task.mark_as_doing()
    await task.save()

    return task


async def test_death_before_start_re_enqueues_without_burning_a_retry(setup_db: FastEdgy) -> None:
    task = await _doing_task()

    await get_service(QueueWorkerManager)._requeue_after_worker_death(task.id, started=False)
    reloaded = await queue().get_task_by_id(task.id)

    assert reloaded is not None
    assert reloaded.state == QueuedTaskState.enqueued
    assert reloaded.retry_count == 0


async def test_death_while_running_counts_an_attempt(setup_db: FastEdgy) -> None:
    task = await _doing_task(max_retries=3)

    await get_service(QueueWorkerManager)._requeue_after_worker_death(task.id, started=True)
    reloaded = await queue().get_task_by_id(task.id)

    assert reloaded is not None
    assert reloaded.state == QueuedTaskState.enqueued
    assert reloaded.retry_count == 1


async def test_death_while_running_fails_once_the_budget_is_spent(setup_db: FastEdgy) -> None:
    task = await _doing_task(max_retries=0)

    await get_service(QueueWorkerManager)._requeue_after_worker_death(task.id, started=True)
    reloaded = await queue().get_task_by_id(task.id)

    assert reloaded is not None
    assert reloaded.state == QueuedTaskState.failed
    assert reloaded.exception_name == "WorkerProcessDied"


async def test_a_finalized_task_is_never_resurrected(setup_db: FastEdgy) -> None:
    task = await _doing_task()
    task.mark_as_done()
    await task.save()

    await get_service(QueueWorkerManager)._requeue_after_worker_death(task.id, started=True)
    reloaded = await queue().get_task_by_id(task.id)

    assert reloaded is not None
    assert reloaded.state == QueuedTaskState.done


def record_kills(pool: WorkerPool) -> list[int]:
    killed: list[int] = []
    pool._signal = lambda worker, sig: killed.append(worker.index)  # type: ignore[assignment,method-assign]

    return killed


def silence(worker: WorkerProcess, seconds: float) -> None:
    worker.last_beat = asyncio.get_event_loop().time() - seconds


async def test_an_idle_worker_that_stops_beating_is_killed(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    killed = record_kills(pool)
    silence(workers[0], IDLE_WEDGE_TIMEOUT + 10)

    assert pool.reap_wedged_workers() == 1
    assert killed == [0]


async def test_a_beating_worker_is_left_alone(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=2)
    killed = record_kills(pool)
    silence(workers[0], IDLE_WEDGE_TIMEOUT - 10)

    assert pool.reap_wedged_workers() == 0
    assert killed == []


async def test_a_busy_worker_gets_the_task_timeout_budget(
    setup_db: FastEdgy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, workers = build_pool(workers_count=1)
    monkeypatch.setattr(pool.config, "task_timeout", 300)
    killed = record_kills(pool)
    workers[0].runs[1] = WorkerSlot(pool, 1)
    silence(workers[0], IDLE_WEDGE_TIMEOUT + 10)

    assert pool.reap_wedged_workers() == 0

    silence(workers[0], 300 * 2 + 10)

    assert pool.reap_wedged_workers() == 1
    assert killed == [0]


async def test_a_worker_that_never_boots_is_killed_after_the_grace(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    killed = record_kills(pool)
    workers[0].last_beat = None
    workers[0].spawned_at = asyncio.get_event_loop().time() - (BOOT_GRACE - 10)

    assert pool.reap_wedged_workers() == 0

    workers[0].spawned_at = asyncio.get_event_loop().time() - (BOOT_GRACE + 10)

    assert pool.reap_wedged_workers() == 1
    assert killed == [0]


async def test_no_worker_is_reaped_while_draining(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=1)
    killed = record_kills(pool)
    silence(workers[0], IDLE_WEDGE_TIMEOUT + 60)
    pool.draining = True

    assert pool.reap_wedged_workers() == 0
    assert killed == []


async def test_a_heartbeat_message_refreshes_the_worker(setup_db: FastEdgy) -> None:
    from fastedgy.queued_task.services.worker_process import MSG_HEARTBEAT

    pool, workers = build_pool(workers_count=1)
    silence(workers[0], IDLE_WEDGE_TIMEOUT + 10)
    pool._handle(workers[0], (MSG_HEARTBEAT, 0))

    assert pool.reap_wedged_workers() == 0


async def test_a_pool_that_has_not_started_reports_no_missing_worker(setup_db: FastEdgy) -> None:
    pool = WorkerPool(workers=6, concurrency=2)

    assert pool.all_workers_alive is True


async def test_a_started_pool_reports_its_missing_workers(setup_db: FastEdgy) -> None:
    pool, workers = build_pool(workers_count=2)
    pool._started = True

    assert pool.all_workers_alive is True

    workers[0].alive = False

    assert pool.all_workers_alive is False


async def test_the_liveness_file_survives_the_database_wait(
    setup_db: FastEdgy,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = get_service(QueueWorkerManager)
    health = tmp_path / "health"
    monkeypatch.setattr(manager.config, "health_file", str(health))
    monkeypatch.setattr(manager, "is_running", True)
    monkeypatch.setattr(manager, "worker_pool", WorkerPool(workers=6, concurrency=2))

    manager._touch_health_file()

    assert health.exists()


async def test_the_liveness_file_is_withheld_once_a_started_pool_is_empty(
    setup_db: FastEdgy,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = get_service(QueueWorkerManager)
    health = tmp_path / "health"
    pool, workers = build_pool(workers_count=1)
    pool._started = True
    workers[0].alive = False
    monkeypatch.setattr(manager.config, "health_file", str(health))
    monkeypatch.setattr(manager, "is_running", True)
    monkeypatch.setattr(manager, "worker_pool", pool)

    manager._touch_health_file()

    assert not health.exists()
