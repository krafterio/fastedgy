# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
import multiprocessing
import os
import signal
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import TYPE_CHECKING, Any

from fastedgy.dependencies import get_service
from fastedgy.queued_task.config import QueuedTaskConfig
from fastedgy.queued_task.services.worker_process import (
    ENV_WORKER_PROCESS,
    HEARTBEAT_INTERVAL,
    MSG_HEARTBEAT,
    MSG_RESULT,
    MSG_RUN,
    MSG_STARTED,
    MSG_STOP,
    MSG_SYNC_FINISHED,
    STATUS_WORKER_DIED,
    run_worker_process,
)

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


logger = logging.getLogger("queued_task.worker_pool")

IDLE_WEDGE_TIMEOUT = 60.0
BOOT_GRACE = 120.0
RESPONSIVE_WINDOW = HEARTBEAT_INTERVAL * 3


class WorkerSlot:
    """A unit of task concurrency, executed by one of the pool's workers."""

    def __init__(self, pool: "WorkerPool", slot_id: int):
        self.slot_id = slot_id
        self.worker_id = f"slot_{slot_id}"
        self.current_task: "QueuedTask | None" = None
        self.pending_sync_finished: asyncio.Event | None = None
        self.started = False
        self._pool = pool
        self._result: asyncio.Future[dict[str, Any]] | None = None

    async def run_task(self, task: "QueuedTask") -> dict[str, Any]:
        self.current_task = task
        self.started = False
        self.pending_sync_finished = None

        process = self._pool.pick_worker()

        if process is None:
            self.current_task = None

            return {"status": STATUS_WORKER_DIED, "started": False, "error": "no live worker"}

        run_id = self._pool.next_run_id()
        self._result = asyncio.get_running_loop().create_future()
        process.runs[run_id] = self

        try:
            if not process.send((MSG_RUN, run_id, task.id)):
                return {"status": STATUS_WORKER_DIED, "started": False, "error": "worker pipe closed"}

            result = await self._result

            if result.get("pending_sync"):
                self.pending_sync_finished = asyncio.Event()
                process.pending_sync[run_id] = self.pending_sync_finished

            return result
        finally:
            process.runs.pop(run_id, None)
            self._result = None
            self.current_task = None

    def on_started(self) -> None:
        self.started = True

    def on_result(self, result: dict[str, Any]) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_result(result)

    def on_process_death(self) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_result(
                {
                    "status": STATUS_WORKER_DIED,
                    "started": self.started,
                    "error": "worker died",
                }
            )

    def __str__(self):
        return f"WorkerSlot({self.slot_id}, busy={self.current_task is not None})"


class WorkerProcess:
    """One spawned worker process and the pipe used to drive it."""

    def __init__(self, index: int, process: BaseProcess, conn: Connection, spawned_at: float):
        self.index = index
        self.process = process
        self.conn = conn
        self.runs: dict[int, WorkerSlot] = {}
        self.pending_sync: dict[int, asyncio.Event] = {}
        self.alive = True
        self.spawned_at = spawned_at
        self.last_beat: float | None = None

    def send(self, message: Any) -> bool:
        try:
            self.conn.send(message)

            return True
        except BrokenPipeError, EOFError, OSError:
            return False

    @property
    def load(self) -> int:
        return len(self.runs)


class WorkerPool:
    """Dispatches claimed tasks to a fixed set of worker processes."""

    def __init__(self, workers: int | None = None, concurrency: int | None = None):
        self.config = get_service(QueuedTaskConfig)
        self.workers = max(workers or self.config.workers, 1)
        self.concurrency = max(concurrency or self.config.concurrency, 1)
        self.busy_workers: dict[str, WorkerSlot] = {}
        self.shutdown_grace = 10.0
        self.draining = False
        self._idle_slots: list[WorkerSlot] = []
        self._next_slot_id = 0
        self._next_run_id = 0
        self._workers: dict[int, WorkerProcess] = {}
        self._shutting_down = False
        self._started = False
        self._mp = multiprocessing.get_context("spawn")

    @property
    def max_slots(self) -> int:
        return self.workers * self.concurrency

    async def start(self) -> None:
        logger.info(f"Starting {self.workers} worker(s), {self.concurrency} concurrent task(s) each")

        for index in range(self.workers):
            self._spawn(index)

        self._started = True

    @property
    def idle_workers(self) -> int:
        return len(self._idle_slots)

    @property
    def live_workers(self) -> int:
        return sum(1 for worker in self._workers.values() if worker.alive)

    @property
    def all_workers_alive(self) -> bool:
        """A pool that has not started yet is not missing anything: the manager
        keeps the liveness file fresh while it waits for the database."""
        return not self._started or self.live_workers >= self.workers

    def next_run_id(self) -> int:
        self._next_run_id += 1

        return self._next_run_id

    def pick_worker(self) -> WorkerProcess | None:
        """Least loaded worker, skipping silent ones: a wedged worker holds
        nothing, so it would otherwise attract every new task."""
        candidates = [worker for worker in self._workers.values() if worker.alive]

        if not candidates:
            return None

        now = asyncio.get_running_loop().time()
        responsive = [
            worker
            for worker in candidates
            if worker.last_beat is not None and now - worker.last_beat <= RESPONSIVE_WINDOW
        ]

        return min(responsive or candidates, key=lambda worker: worker.load)

    async def get_available_worker(self) -> WorkerSlot | None:
        if self.draining or self._shutting_down or not self.live_workers:
            return None

        if self._idle_slots:
            slot = self._idle_slots.pop()
        elif len(self.busy_workers) < self.max_slots:
            slot = WorkerSlot(self, self._next_slot_id)
            self._next_slot_id += 1
            logger.debug(f"Created slot {slot.worker_id} ({len(self.busy_workers) + 1}/{self.max_slots})")
        else:
            logger.debug(f"Worker pool full ({self.max_slots}); task waits for next cycle")

            return None

        self.busy_workers[slot.worker_id] = slot

        return slot

    async def return_worker(self, worker: WorkerSlot) -> None:
        self.busy_workers.pop(worker.worker_id, None)

        if not self.draining and not self._shutting_down:
            self._idle_slots.append(worker)

    async def get_pool_stats(self) -> dict[str, int]:
        return {
            "max_workers": self.max_slots,
            "workers": self.workers,
            "live_workers": self.live_workers,
            "concurrency": self.concurrency,
            "busy_workers": len(self.busy_workers),
            "idle_workers": self.idle_workers,
            "total_workers": len(self.busy_workers) + self.idle_workers,
        }

    def get_busy_workers(self) -> list[WorkerSlot]:
        return list(self.busy_workers.values())

    def reap_wedged_workers(self) -> int:
        """Kill workers whose event loop stopped turning; the closed pipe then
        drives the usual death path. Idle, a worker must beat. Busy, only twice
        task_timeout is conclusive: a CPU-bound body blocks its loop too."""
        if self.draining or self._shutting_down:
            return 0

        now = asyncio.get_running_loop().time()
        busy_timeout = max(int(self.config.task_timeout or 0), 1) * 2
        reaped = 0

        for worker in list(self._workers.values()):
            if not worker.alive:
                continue

            if worker.last_beat is None:
                if now - worker.spawned_at <= BOOT_GRACE:
                    continue

                silent_for = now - worker.spawned_at
                reason = "never finished starting up"
            else:
                silent_for = now - worker.last_beat
                timeout = busy_timeout if worker.runs else IDLE_WEDGE_TIMEOUT

                if silent_for <= timeout:
                    continue

                reason = "event loop stopped responding"

            logger.error(
                f"Worker {worker.index} {reason} ({silent_for:.0f}s without a heartbeat, "
                f"{len(worker.runs)} task(s) in flight), killing it"
            )
            self._signal(worker, signal.SIGKILL)
            reaped += 1

        return reaped

    async def shutdown(self) -> None:
        """Stop every worker, letting in-flight tasks mark themselves stopped."""
        if self._shutting_down:
            return

        self._shutting_down = True
        self.draining = True
        logger.info("Shutting down worker pool...")

        for worker in self._workers.values():
            if worker.alive and not worker.send((MSG_STOP,)):
                self._signal(worker, signal.SIGTERM)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.shutdown_grace

        while any(worker.alive for worker in self._workers.values()) and loop.time() < deadline:
            await asyncio.sleep(0.1)

        for worker in self._workers.values():
            if worker.alive:
                logger.warning(f"Worker {worker.index} did not stop in time, killing it")
                self._signal(worker, signal.SIGKILL)

        for worker in list(self._workers.values()):
            self._release(worker)
            worker.process.join(timeout=1)

        self._workers.clear()
        self._idle_slots.clear()
        self.busy_workers.clear()
        logger.info("Worker pool shutdown complete")

    def _spawn(self, index: int) -> None:
        parent_conn, child_conn = self._mp.Pipe(duplex=True)
        process = self._mp.Process(
            target=run_worker_process,
            args=(child_conn, index, self._child_env(), self.shutdown_grace),
            name=f"queue-worker-{index}",
        )
        process.start()
        child_conn.close()

        worker = WorkerProcess(index, process, parent_conn, asyncio.get_running_loop().time())
        self._workers[index] = worker
        asyncio.get_running_loop().add_reader(parent_conn.fileno(), self._on_readable, worker)
        logger.info(f"Worker {index} started (pid {process.pid})")

    def _child_env(self) -> dict[str, str]:
        env: dict[str, str] = {ENV_WORKER_PROCESS: "1"}
        overrides = (
            ("DATABASE_POOL_SIZE", self.config.worker_db_pool_size),
            ("DATABASE_MAX_OVERFLOW", self.config.worker_db_max_overflow),
            ("QUEUED_TASK_MANAGER_DB_POOL_SIZE", self.config.worker_manager_db_pool_size),
            ("QUEUED_TASK_MANAGER_DB_MAX_OVERFLOW", self.config.worker_manager_db_max_overflow),
        )

        for name, value in overrides:
            if value is not None:
                env[name] = str(value)

        return env

    def _on_readable(self, worker: WorkerProcess) -> None:
        try:
            while worker.conn.poll():
                self._handle(worker, worker.conn.recv())
        except EOFError, OSError:
            self._on_process_death(worker)

    def _handle(self, worker: WorkerProcess, message: Any) -> None:
        kind, run_id = message[0], message[1]

        if kind == MSG_HEARTBEAT:
            worker.last_beat = asyncio.get_running_loop().time()

            return

        if kind == MSG_SYNC_FINISHED:
            finished = worker.pending_sync.pop(run_id, None)

            if finished is not None:
                finished.set()

            return

        slot = worker.runs.get(run_id)

        if slot is None:
            return

        if kind == MSG_STARTED:
            slot.on_started()
        elif kind == MSG_RESULT:
            slot.on_result(message[2])

    def _on_process_death(self, worker: WorkerProcess) -> None:
        if not worker.alive:
            return

        worker.alive = False
        self._release(worker)
        worker.process.join(timeout=1)

        if self.draining or self._shutting_down:
            logger.info(f"Worker {worker.index} exited (code {worker.process.exitcode})")

            return

        logger.error(f"Worker {worker.index} died (exit code {worker.process.exitcode}), respawning")
        self._workers.pop(worker.index, None)

        try:
            self._spawn(worker.index)
        except Exception as e:
            logger.error(f"Failed to respawn worker {worker.index}: {e}")

    def _release(self, worker: WorkerProcess) -> None:
        """Detach a worker and unblock everything waiting on it."""
        try:
            asyncio.get_running_loop().remove_reader(worker.conn.fileno())
        except Exception:
            pass

        try:
            worker.conn.close()
        except Exception:
            pass

        for slot in list(worker.runs.values()):
            slot.on_process_death()

        worker.runs.clear()

        for finished in worker.pending_sync.values():
            finished.set()

        worker.pending_sync.clear()

    def _signal(self, worker: WorkerProcess, sig: int) -> None:
        pid = worker.process.pid

        if pid is None:
            return

        try:
            os.kill(pid, sig)
        except ProcessLookupError, PermissionError:
            pass
        except OSError as e:
            logger.error(f"Cannot signal worker {worker.index}: {e}")

    def __str__(self):
        return (
            f"WorkerPool(slots={self.max_slots}, workers={self.live_workers}/{self.workers}, "
            f"busy={len(self.busy_workers)}, idle={self.idle_workers})"
        )
