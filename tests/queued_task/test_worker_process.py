# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import multiprocessing
from typing import Any

import pytest

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.services.worker_pool import WorkerPool, WorkerProcess, WorkerSlot
from fastedgy.queued_task.services.worker_process import (
    MSG_HEARTBEAT,
    MSG_RESULT,
    MSG_RUN,
    MSG_STARTED,
    MSG_STOP,
    MSG_SYNC_FINISHED,
    _run_task,
    _serve,
)

from .helpers import queue


class FakeProcess:
    def __init__(self) -> None:
        self.pid = None
        self.exitcode = 0

    def join(self, timeout: float | None = None) -> None:
        pass


class Wiring:
    """A pool and a worker talking over a real pipe, both in this process."""

    def __init__(self, pool: WorkerPool, worker: WorkerProcess, child_conn: Any) -> None:
        self.pool = pool
        self.worker = worker
        self.child_conn = child_conn

    def pump(self) -> None:
        self.pool._on_readable(self.worker)

    async def settle(self) -> None:
        for _ in range(5):
            self.pump()
            await asyncio.sleep(0)


def wire() -> Wiring:
    pool = WorkerPool(workers=1, concurrency=2)
    parent_conn, child_conn = multiprocessing.Pipe(duplex=True)
    worker = WorkerProcess(0, FakeProcess(), parent_conn, asyncio.get_event_loop().time())  # type: ignore[arg-type]
    pool._workers[0] = worker

    return Wiring(pool, worker, child_conn)


async def claim_slot(wiring: Wiring) -> WorkerSlot:
    slot = await wiring.pool.get_available_worker()
    assert slot is not None

    return slot


async def doing_task(**kwargs: Any) -> tuple[Any, int]:
    task = await queue().create_task(module_name="fastedgy.test.tasks", **kwargs)
    task.mark_as_doing()
    await task.save()

    assert task.id is not None

    return task, task.id


async def test_worker_reports_started_then_result(setup_db: FastEdgy) -> None:
    wiring = wire()
    task, task_id = await doing_task(function_name="add_numbers", args=[2, 3])
    slot = await claim_slot(wiring)
    job = asyncio.create_task(slot.run_task(task))
    await asyncio.sleep(0)

    run_id = next(iter(wiring.worker.runs))
    await _run_task(wiring.child_conn, 0, run_id, task_id)
    await wiring.settle()

    assert slot.started is True
    assert (await job)["status"] == "success"

    reloaded = await queue().get_task_by_id(task_id)
    assert reloaded is not None
    assert reloaded.state == QueuedTaskState.done


async def test_worker_reports_a_missing_task_without_claiming_it_started(setup_db: FastEdgy) -> None:
    wiring = wire()
    task, task_id = await doing_task(function_name="add_numbers")
    slot = await claim_slot(wiring)
    job = asyncio.create_task(slot.run_task(task))
    await asyncio.sleep(0)

    run_id = next(iter(wiring.worker.runs))
    await task.delete()
    await _run_task(wiring.child_conn, 0, run_id, task_id)
    await wiring.settle()

    assert (await job)["status"] == "not_found"
    assert slot.started is False


async def test_a_failing_task_reports_its_error(setup_db: FastEdgy) -> None:
    wiring = wire()
    task, task_id = await doing_task(function_name="boom", max_retries=0)
    slot = await claim_slot(wiring)
    job = asyncio.create_task(slot.run_task(task))
    await asyncio.sleep(0)

    run_id = next(iter(wiring.worker.runs))
    await _run_task(wiring.child_conn, 0, run_id, task_id)
    await wiring.settle()

    assert (await job)["status"] != "success"
    assert slot.started is True


async def test_a_timed_out_sync_task_holds_its_slot_until_its_thread_ends(
    setup_db: FastEdgy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastedgy.test import tasks as test_tasks

    test_tasks.reset_blocking_sync()
    wiring = wire()
    monkeypatch.setattr(wiring.pool.config, "task_timeout", 1)

    task, task_id = await doing_task(function_name="blocking_sync", args=[30.0], max_retries=0)
    slot = await claim_slot(wiring)
    job = asyncio.create_task(slot.run_task(task))
    await asyncio.sleep(0)

    run_id = next(iter(wiring.worker.runs))
    runner = asyncio.create_task(_run_task(wiring.child_conn, 0, run_id, task_id))

    try:
        result = await asyncio.wait_for(job_with_pump(job, wiring), timeout=15)

        assert result["pending_sync"] is True
        assert slot.pending_sync_finished is not None
        assert not slot.pending_sync_finished.is_set()

        test_tasks.release_blocking_sync()
        await asyncio.wait_for(runner, timeout=10)
        await wiring.settle()

        assert slot.pending_sync_finished.is_set()
    finally:
        test_tasks.release_blocking_sync()

        if not runner.done():
            await asyncio.wait_for(runner, timeout=10)


async def job_with_pump(job: asyncio.Task, wiring: Wiring) -> Any:
    while not job.done():
        wiring.pump()
        await asyncio.sleep(0.05)

    return await job


async def test_worker_beats_while_it_serves(setup_db: FastEdgy) -> None:
    wiring = wire()
    shutdown = asyncio.Event()
    server = asyncio.create_task(_serve(wiring.child_conn, shutdown, 0, 1.0))

    await asyncio.sleep(0.1)
    await wiring.settle()

    assert wiring.worker.last_beat is not None

    shutdown.set()
    await asyncio.wait_for(server, timeout=5)


async def test_worker_stops_on_the_stop_message(setup_db: FastEdgy) -> None:
    wiring = wire()
    shutdown = asyncio.Event()
    server = asyncio.create_task(_serve(wiring.child_conn, shutdown, 0, 1.0))

    await asyncio.sleep(0.05)
    wiring.worker.conn.send((MSG_STOP,))
    await asyncio.wait_for(server, timeout=5)

    assert shutdown.is_set()


async def test_worker_stops_when_the_manager_pipe_closes(setup_db: FastEdgy) -> None:
    wiring = wire()
    shutdown = asyncio.Event()
    server = asyncio.create_task(_serve(wiring.child_conn, shutdown, 0, 1.0))

    await asyncio.sleep(0.05)
    wiring.worker.conn.close()
    await asyncio.wait_for(server, timeout=5)

    assert shutdown.is_set()


async def test_worker_runs_a_task_sent_over_the_pipe(setup_db: FastEdgy) -> None:
    wiring = wire()
    _task, task_id = await doing_task(function_name="add_numbers", args=[4, 5])
    shutdown = asyncio.Event()
    server = asyncio.create_task(_serve(wiring.child_conn, shutdown, 0, 1.0))
    seen: list[Any] = []

    wiring.worker.conn.send((MSG_RUN, 7, task_id))

    for _ in range(200):
        while wiring.worker.conn.poll():
            seen.append(wiring.worker.conn.recv())

        if any(message[0] == MSG_RESULT for message in seen):
            break

        await asyncio.sleep(0.05)

    shutdown.set()
    await asyncio.wait_for(server, timeout=5)

    kinds = [message[0] for message in seen if message[0] != MSG_HEARTBEAT]

    assert kinds == [MSG_STARTED, MSG_RESULT]
    assert seen[-1][1] == 7
    assert MSG_SYNC_FINISHED not in kinds
