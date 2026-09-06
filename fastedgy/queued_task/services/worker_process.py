# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
import os
import signal
from multiprocessing.connection import Connection
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


logger = logging.getLogger("queued_task.worker_process")

MSG_RUN = "run"
MSG_STOP = "stop"
MSG_STARTED = "started"
MSG_RESULT = "result"
MSG_SYNC_FINISHED = "sync_finished"
MSG_HEARTBEAT = "heartbeat"

HEARTBEAT_INTERVAL = 10.0

STATUS_WORKER_DIED = "worker_died"

ENV_WORKER_PROCESS = "FASTEDGY_QUEUE_WORKER_PROCESS"


def is_worker_process() -> bool:
    """Whether the current process is a queue worker, for lifespan branching."""
    return os.environ.get(ENV_WORKER_PROCESS) == "1"


def run_worker_process(
    conn: Connection,
    index: int,
    env_overrides: dict[str, str],
    shutdown_grace: float,
) -> None:
    for key, value in env_overrides.items():
        os.environ[key] = value

    try:
        asyncio.run(_worker_main(conn, index, shutdown_grace))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def _worker_main(conn: Connection, index: int, shutdown_grace: float) -> None:
    from fastedgy.config import BaseSettings, init_settings
    from fastedgy.dependencies import get_service
    from fastedgy.logger import setup_logging
    from fastedgy.modules import import_from_string
    from fastedgy.queued_task.config import QueuedTaskConfig
    from fastedgy.queued_task.logging import QueuedTaskLogger, configure_queued_task_logging

    settings = init_settings()
    setup_logging(
        level=settings.log_level,
        output=settings.log_output,
        format=settings.log_format,
        log_file=settings.log_path,
    )

    app = import_from_string(settings.app_factory)()
    app.initialize()

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: shutdown.set())

    async with app.router.lifespan_context(app):
        configure_queued_task_logging(get_service(BaseSettings))
        config = get_service(QueuedTaskConfig)
        await config.init_manager_registry()
        logger.info(f"Worker {index} ready (pid {os.getpid()})")

        try:
            await _serve(conn, shutdown, index, shutdown_grace)
        finally:
            try:
                await QueuedTaskLogger.drain_pending_db_logs()
            except Exception as e:
                logger.error(f"Error draining pending DB logs: {e}")

            try:
                await config.close_manager_registry()
            except Exception as e:
                logger.error(f"Error closing manager registry: {e}")

    logger.info(f"Worker {index} stopped")


async def _heartbeat(conn: Connection, shutdown: asyncio.Event) -> None:
    """Beat from the event loop itself, so a blocked loop stops beating."""
    while not shutdown.is_set():
        _send(conn, (MSG_HEARTBEAT, 0))

        try:
            await asyncio.wait_for(shutdown.wait(), timeout=HEARTBEAT_INTERVAL)
        except TimeoutError:
            pass


async def _serve(conn: Connection, shutdown: asyncio.Event, index: int, shutdown_grace: float) -> None:
    loop = asyncio.get_running_loop()
    running: dict[int, asyncio.Task] = {}
    closed = asyncio.Event()

    def on_readable() -> None:
        try:
            while conn.poll():
                message = conn.recv()
                _dispatch(message)
        except EOFError, OSError:
            closed.set()
            shutdown.set()

    def _dispatch(message: Any) -> None:
        kind = message[0]

        if kind == MSG_RUN:
            run_id, task_id = message[1], message[2]
            job = asyncio.create_task(_run_task(conn, index, run_id, task_id))
            running[run_id] = job
            job.add_done_callback(lambda _t, rid=run_id: running.pop(rid, None))
        elif kind == MSG_STOP:
            shutdown.set()

    loop.add_reader(conn.fileno(), on_readable)
    heartbeat = asyncio.create_task(_heartbeat(conn, shutdown))

    try:
        await shutdown.wait()
    finally:
        heartbeat.cancel()

        try:
            loop.remove_reader(conn.fileno())
        except Exception:
            pass

    in_flight = [job for job in running.values() if not job.done()]

    if in_flight:
        logger.info(f"Worker {index} cancelling {len(in_flight)} in-flight task(s)")

        for job in in_flight:
            job.cancel()

        try:
            await asyncio.wait(in_flight, timeout=shutdown_grace)
        except Exception:
            pass


async def _run_task(conn: Connection, index: int, run_id: int, task_id: int) -> None:
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry
    from fastedgy.queued_task.services.queue_worker import QueueWorker

    result: dict[str, Any] = {"status": "error", "error": "worker did not report"}
    pending_sync: asyncio.Event | None = None

    try:
        registry = get_service(Registry)
        QueuedTask = cast(type["QueuedTask"], registry.get_model("QueuedTask"))
        task = await QueuedTask.query.filter(QueuedTask.columns.id == task_id).get_or_none()

        if task is None:
            _send(conn, (MSG_RESULT, run_id, {"status": "not_found", "task_id": task_id}))

            return

        _send(conn, (MSG_STARTED, run_id))

        worker = QueueWorker(f"worker_{index}_{run_id}")
        result = await worker.run_task(task)
        pending_sync = worker.pending_sync_finished
        worker.pending_sync_finished = None

        if pending_sync is not None and not pending_sync.is_set():
            result["pending_sync"] = True
        else:
            pending_sync = None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Worker {index} failed to run task {task_id}: {e}")
        result = {"status": "error", "error": str(e)}

    # The manager arms the event on this result: notify only once it is sent.
    _send(conn, (MSG_RESULT, run_id, result))

    if pending_sync is not None:
        asyncio.create_task(_notify_sync_finished(conn, run_id, pending_sync))


async def _notify_sync_finished(conn: Connection, run_id: int, finished: asyncio.Event) -> None:
    await finished.wait()
    _send(conn, (MSG_SYNC_FINISHED, run_id))


def _send(conn: Connection, message: Any) -> None:
    try:
        conn.send(message)
    except BrokenPipeError, EOFError, OSError:
        pass
