# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

import signal

import socket

import logging

from datetime import datetime, timedelta

from typing import TYPE_CHECKING, Optional, Dict, Any, List, cast

from fastedgy import context
from fastedgy.dependencies import Inject, get_service
from fastedgy.orm import Database, Registry
from fastedgy.queued_task.config import QueuedTaskConfig
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.services.worker_pool import WorkerPool
from fastedgy.queued_task.scheduler.cron_scheduler import CronScheduler


if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask
    from fastedgy.models.queued_task_worker import (
        BaseQueuedTaskWorker as QueuedTaskWorker,
    )


logger = logging.getLogger("queued_task.manager")


class QueueWorkerManager:
    """
    Main manager for the queue worker system

    Handles:
    - PostgreSQL NOTIFY/LISTEN for instant reactivity
    - Fallback polling for robustness
    - Worker pool management
    - Task distribution
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        server_name: Optional[str] = None,
        registry: Registry = Inject(Registry),
        config: QueuedTaskConfig = Inject(QueuedTaskConfig),
        database: Database = Inject(Database),
    ):
        self.registry = registry
        self.config = config
        self.database = database
        self.max_workers = max_workers or self.config.max_workers
        self.server_name = server_name or socket.gethostname()
        self.worker_pool = WorkerPool(self.max_workers)
        self.is_running = False
        self.manager_tasks: List[asyncio.Task] = []
        self.worker_status_record: Optional["QueuedTaskWorker"] = None
        self.cron_scheduler: Optional[CronScheduler] = None
        self.shutdown_event = asyncio.Event()

        # Statistics
        self.stats = {
            "started_at": None,
            "tasks_processed": 0,
            "tasks_failed": 0,
            "notifications_received": 0,
            "polling_cycles": 0,
        }

    async def start_workers(
        self, max_workers: Optional[int] = None, no_scheduler: bool = False
    ) -> None:
        """
        Start the worker manager system

        Args:
            max_workers: Override max workers for this session
        """
        if self.is_running:
            logger.warning("Worker manager is already running")
            return

        self._configure_logging()

        if max_workers:
            self.max_workers = max_workers
            self.worker_pool.max_workers = max_workers

        self.is_running = True
        self.stats["started_at"] = datetime.now(context.get_timezone())

        logger.info(f"Starting QueueWorkerManager with {self.max_workers} max workers")

        # Initialize database triggers and functions
        try:
            await self._init_db()
        except Exception as e:
            self.is_running = False
            logger.error(f"Failed to initialize database, aborting worker startup: {e}")
            raise RuntimeError(f"Queue system initialization failed: {e}")

        # Initialize dedicated manager registry for queue operations
        # (separate DB connection to avoid transaction conflicts)
        try:
            await self.config.init_manager_registry()
            logger.info(
                "Manager registry initialized with dedicated database connection"
            )
        except Exception as e:
            self.is_running = False
            logger.error(f"Failed to initialize manager registry: {e}")
            raise RuntimeError(f"Manager registry initialization failed: {e}")

        # Register this server in the database
        await self._register_server()

        # Recover tasks orphaned in 'doing' by a previous non-graceful shutdown
        try:
            await self._recover_orphaned_doing_tasks()
        except Exception as e:
            logger.error(f"Orphaned 'doing' tasks recovery failed: {e}")

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Start all manager tasks
        self.manager_tasks = [
            asyncio.create_task(
                self._notification_listener(), name="notification_listener"
            ),
            asyncio.create_task(self._fallback_polling(), name="fallback_polling"),
            asyncio.create_task(
                self._cleanup_idle_workers(), name="cleanup_idle_workers"
            ),
            asyncio.create_task(self._heartbeat_task(), name="heartbeat_task"),
        ]

        # Conditionally start CronScheduler
        if not no_scheduler:
            self.cron_scheduler = CronScheduler()
            self.manager_tasks.append(
                asyncio.create_task(self.cron_scheduler.run(), name="cron_scheduler")
            )
        else:
            logger.info("CronScheduler disabled (--no-scheduler)")

        logger.info("QueueWorkerManager started successfully")

        # Wait for shutdown signal or task completion
        try:
            # Kickstart: process pending tasks immediately on startup
            try:
                await self._process_pending_tasks()
            except Exception as e:
                logger.error(f"Initial pending tasks processing failed: {e}")

            # Wait for either all manager tasks to complete or shutdown signal
            done, pending = await asyncio.wait(
                self.manager_tasks + [asyncio.create_task(self.shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except asyncio.CancelledError:
            logger.info("Worker manager tasks cancelled")
        finally:
            # Ensure clean shutdown
            if self.is_running:
                await self.stop_workers()

    async def stop_workers(self) -> None:
        """Stop the worker manager system"""
        if not self.is_running:
            return

        logger.info("Stopping QueueWorkerManager...")
        self.is_running = False

        # Stop CronScheduler if running
        if self.cron_scheduler:
            self.cron_scheduler.stop()
            self.cron_scheduler = None

        # Mark in-progress tasks as stopped before pool shutdown
        for worker in self.worker_pool.get_busy_workers():
            if worker.current_task:
                try:
                    from sqlalchemy import text

                    sql = text(
                        "UPDATE queued_tasks SET state = 'stopped'::queuedtaskstate, "
                        "date_stopped = NOW(), date_ended = NOW(), "
                        "execution_time = EXTRACT(EPOCH FROM (NOW() - COALESCE(date_started, NOW()))), "
                        "updated_at = NOW() "
                        "WHERE id = :id AND state = 'doing'::queuedtaskstate"
                    )
                    await self.database.execute(sql, {"id": worker.current_task.id})
                    logger.info(
                        f"Marked task {worker.current_task.id} as stopped (graceful shutdown)"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to mark task {worker.current_task.id} as stopped: {e}"
                    )

        # Cancel all manager tasks
        for task in self.manager_tasks:
            task.cancel()

        # Fast wait with timeout to avoid long shutdown delays
        if self.manager_tasks:
            try:
                await asyncio.wait(self.manager_tasks, timeout=2)
            except Exception:
                pass

        # Shutdown worker pool
        await self.worker_pool.shutdown()

        # Mark server as stopped in database
        await self._unregister_server()

        # Close manager registry database connection
        try:
            await self.config.close_manager_registry()
            logger.debug("Manager registry closed")
        except Exception as e:
            logger.error(f"Error closing manager registry: {e}")

        self.manager_tasks.clear()
        logger.info("QueueWorkerManager stopped")

        # Reduce noisy SQLAlchemy termination logs during engine dispose
        try:
            logging.getLogger("sqlalchemy.pool.base").setLevel(logging.CRITICAL)
            logging.getLogger("sqlalchemy.dialects.postgresql.asyncpg").setLevel(
                logging.CRITICAL
            )
        except Exception:
            pass

    def _configure_logging(self) -> None:
        """Configure logging levels for queued task loggers."""
        from fastedgy.config import BaseSettings

        settings = get_service(BaseSettings)

        if settings.queued_task_log_level is not None:
            target_level = getattr(
                logging, settings.queued_task_log_level.value.upper()
            )
        else:
            root_level = logging.getLogger().level

            if root_level == logging.NOTSET:
                target_level = getattr(logging, settings.log_level.value.upper())
            else:
                target_level = root_level

        logging.getLogger("queued_task.context").setLevel(target_level)
        logging.getLogger("queued_task.hooks").setLevel(target_level)
        logging.getLogger("queued_task.manager").setLevel(target_level)
        logging.getLogger("queued_task.worker").setLevel(target_level)
        logging.getLogger("queued_task.worker_pool").setLevel(target_level)
        logging.getLogger("queued_tasks").setLevel(target_level)
        logging.getLogger("queued_task.scheduler").setLevel(target_level)

    async def _notification_listener(self) -> None:
        """Listen for PostgreSQL notifications and trigger processing outside the LISTEN connection.

        Uses the raw asyncpg connection add_listener API so that the LISTEN
        connection stays dedicated and task processing runs on separate pooled
        connections.
        """
        if not self.config.use_postgresql_notify:
            logger.info("PostgreSQL NOTIFY/LISTEN disabled in config")
            return

        logger.info(
            f"Starting PostgreSQL notification listener on channel '{self.config.notify_channel}'"
        )

        channel = self.config.notify_channel
        conn_ctx = self.database.connection()
        try:
            async with conn_ctx:
                raw_conn = await conn_ctx.get_raw_connection()

                def _unwrap_asyncpg_connection(conn: Any) -> Any:
                    # Try common attributes used by SQLAlchemy async adapters
                    for attr in ("driver_connection", "dbapi_connection", "connection"):
                        inner = getattr(conn, attr, None)
                        if (
                            inner is not None
                            and hasattr(inner, "add_listener")
                            and hasattr(inner, "remove_listener")
                        ):
                            return inner
                    # Maybe the object itself is an asyncpg connection
                    if hasattr(conn, "add_listener") and hasattr(
                        conn, "remove_listener"
                    ):
                        return conn
                    return None

                pg_conn = _unwrap_asyncpg_connection(raw_conn)
                if pg_conn is None:
                    raise RuntimeError(
                        "Underlying asyncpg connection not accessible; cannot register NOTIFY listener"
                    )

                def on_notify(connection, pid, ch, payload):  # type: ignore[no-untyped-def]
                    try:
                        # Schedule processing immediately outside of the LISTEN connection
                        asyncio.create_task(self._process_pending_tasks())
                    except Exception as cb_err:
                        logger.error(f"Notification callback error: {cb_err}")

                # Register listener (supports sync or async implementations)
                add_listener = getattr(pg_conn, "add_listener", None)
                if add_listener is None:
                    raise RuntimeError("Underlying connection missing add_listener")
                if asyncio.iscoroutinefunction(add_listener):
                    await add_listener(channel, on_notify)  # type: ignore[misc]
                else:
                    add_listener(channel, on_notify)  # type: ignore[misc]
                logger.debug(f"Notification listener registered on channel '{channel}'")

                # Wait until shutdown, but wake up periodically to remain responsive
                while not self.shutdown_event.is_set():
                    await asyncio.sleep(0.1)

                try:
                    remove_listener = getattr(pg_conn, "remove_listener", None)
                    if remove_listener is not None:
                        if asyncio.iscoroutinefunction(remove_listener):
                            await remove_listener(channel, on_notify)  # type: ignore[misc]
                        else:
                            remove_listener(channel, on_notify)  # type: ignore[misc]
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Notification listener error: {e}")
            logger.info("Falling back to polling only - keeping listener task alive")
            # Keep task alive but responsive
            while not self.shutdown_event.is_set():
                await asyncio.sleep(0.1)

    async def _handle_notification(self, task_info: Dict[str, Any]) -> None:
        """
        Handle notification of new task

        Args:
            task_info: Task information dictionary
        """
        try:
            self.stats["notifications_received"] += 1

            task_id = task_info.get("task_id")
            logger.debug(f"📨 Processing notification for task {task_id}")

            # Process pending tasks immediately
            await self._process_pending_tasks()

        except Exception as e:
            logger.error(f"Error handling notification: {e}")

    async def _fallback_polling(self) -> None:
        """Fallback polling to ensure no tasks are missed"""
        logger.info(
            f"Starting fallback polling every {self.config.fallback_polling_interval}s"
        )

        while self.is_running:
            try:
                # Small initial delay to interleave with startup kickstart
                await asyncio.sleep(self.config.fallback_polling_interval)

                if self.is_running:
                    self.stats["polling_cycles"] += 1
                    await self._process_pending_tasks()

            except Exception as e:
                logger.error(f"Fallback polling error: {e}")

    async def _cleanup_idle_workers(self) -> None:
        """Periodic cleanup of idle workers, stale task reaping and stats logging"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Check every minute

                if self.is_running:
                    stats = await self.get_stats()
                    logger.debug(f"Worker stats: {stats['worker_pool']}")
                    await self._reap_stale_tasks()

            except Exception as e:
                logger.error(f"Cleanup task error: {e}")

    async def _process_pending_tasks(self) -> None:
        """Process pending tasks using atomic claim to avoid concurrency conflicts"""
        try:
            while self.is_running:
                # Acquire a worker first; if none, stop here
                worker = await self.worker_pool.get_available_worker()
                if worker is None:
                    logger.debug("No workers available, stop claiming for now")
                    break

                # Atomically claim the next ready task
                task = await self._claim_next_ready_task()
                if task is None:
                    # Nothing to process - return worker to idle and stop
                    await self.worker_pool.return_worker(worker)
                    break

                # Start task execution in background
                logger.debug(
                    f"Assigning claimed task {task.id} to worker {worker.worker_id} (parent: {task.parent_task.id if task.parent_task else 'None'})"
                )
                asyncio.create_task(self._execute_task_with_worker(worker, task))

        except Exception as e:
            logger.error(f"Error processing pending tasks: {e}")

    async def _claim_next_ready_task(self) -> Optional["QueuedTask"]:
        """Atomically claim the next ready task (state=enqueued and parent done) and mark it as doing.

        Uses SELECT .. FOR UPDATE SKIP LOCKED to avoid double-claim across workers/servers.
        Returns the claimed task model or None if none is available.
        """
        try:
            # Use a short transaction with lower isolation to reduce conflicts
            async with self.database.transaction(isolation_level="READ COMMITTED"):
                # Claim the next task atomically and return its id
                from sqlalchemy import text

                sql = text(
                    "WITH next_task AS (\n"
                    "  SELECT qt.id\n"
                    "  FROM queued_tasks qt\n"
                    "  WHERE qt.state = 'enqueued'\n"
                    "    AND (qt.date_enqueued IS NULL OR qt.date_enqueued <= NOW())\n"
                    "    AND (\n"
                    "      qt.parent_task IS NULL\n"
                    "      OR EXISTS (\n"
                    "        SELECT 1 FROM queued_tasks p\n"
                    "        WHERE p.id = qt.parent_task AND p.state = 'done'\n"
                    "      )\n"
                    "    )\n"
                    "  ORDER BY qt.date_enqueued\n"
                    "  FOR UPDATE SKIP LOCKED\n"
                    "  LIMIT 1\n"
                    ")\n"
                    "UPDATE queued_tasks t\n"
                    "SET state = 'doing'::queuedtaskstate, date_started = NOW()\n"
                    "FROM next_task\n"
                    "WHERE t.id = next_task.id\n"
                    "RETURNING t.id"
                )
                row = await self.database.fetch_one(sql)
                if not row:
                    return None

                try:
                    claimed_id = int(row[0])  # type: ignore[index]
                except Exception:
                    try:
                        claimed_id = int(row["id"])  # type: ignore[index]
                    except Exception:
                        claimed_id = None

            if claimed_id is None:
                # As a fallback, re-read the next doing task by date_started very recently assigned to this server window
                # but to avoid complexity, simply indicate none
                return None

            # Load the task model instance. The claim transaction is already
            # committed: if this load fails, the row would stay 'doing' forever
            # while the caller treats None as "nothing to process" — release it
            # back to 'enqueued' before propagating to the outer handler.
            QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
            try:
                task = await QueuedTask.query.filter(
                    QueuedTask.columns.id == claimed_id
                ).get_or_none()
            except Exception:
                await self._release_claimed_task(claimed_id)
                raise
            if task is None:
                # Row deleted between claim and load (concurrent cancel/remove)
                return None
            return task
        except Exception as e:
            logger.error(f"Error claiming next ready task: {e}")
            return None

    async def _release_claimed_task(self, task_id: int) -> None:
        """Best-effort revert of a freshly claimed task back to 'enqueued'.

        Used when the model load right after the claim commit fails: without
        this, the row would stay 'doing' forever (the claim SQL only targets
        'enqueued' and nothing else ever resets it). The state guard keeps the
        UPDATE a no-op if another path already finalized the task.
        """
        try:
            from sqlalchemy import text

            sql = text(
                "UPDATE queued_tasks SET state = 'enqueued'::queuedtaskstate, "
                "date_started = NULL, updated_at = NOW() "
                "WHERE id = :id AND state = 'doing'::queuedtaskstate"
            )
            await self.database.execute(sql, {"id": task_id})
            logger.warning(
                f"Released claimed task {task_id} back to 'enqueued' after load failure"
            )
        except Exception as release_err:
            logger.error(f"Failed to release claimed task {task_id}: {release_err}")

    async def _recover_orphaned_doing_tasks(self) -> None:
        """Boot-time recovery of tasks left in 'doing' by a non-graceful shutdown.

        A graceful shutdown (SIGTERM) marks in-flight tasks as 'stopped' — a
        deliberate terminal state that is only ever restarted manually. Rows
        still in 'doing' at boot therefore come from a hard kill (OOM, SIGKILL,
        crash): without recovery they stay 'doing' forever and silently block
        the cron scheduler dedup for tasks of the same name. Re-enqueue them.

        Multi-server guard: skipped when another alive server exists (its
        'doing' rows are legitimate in-flight work). In that case — and for the
        ~2 min window where a hard-killed sibling still looks alive via its
        last heartbeat — the timeout-based periodic reaper picks them up.
        """
        QueuedTaskWorker = cast(
            type["QueuedTaskWorker"],
            self.registry.get_model("QueuedTaskWorker"),
        )
        alive_threshold = datetime.now(context.get_timezone()) - timedelta(minutes=2)
        other_alive = await QueuedTaskWorker.query.filter(
            QueuedTaskWorker.columns.last_heartbeat >= alive_threshold,
            QueuedTaskWorker.columns.is_running.is_(True),
            QueuedTaskWorker.columns.server_name != self.server_name,
        ).first()
        if other_alive:
            logger.info(
                "Skipping orphaned 'doing' recovery: another alive server detected "
                f"('{other_alive.server_name}') — periodic reaper will handle stale rows"
            )
            return

        from sqlalchemy import text

        sql = text(
            "UPDATE queued_tasks "
            "SET state = 'enqueued'::queuedtaskstate, date_started = NULL, updated_at = NOW() "
            "WHERE state = 'doing'::queuedtaskstate "
            "RETURNING id"
        )
        rows = await self.database.fetch_all(sql)
        if rows:
            ids = [row[0] for row in rows]
            logger.warning(
                f"Recovered {len(ids)} task(s) orphaned in 'doing' by a previous "
                f"non-graceful shutdown, re-enqueued: {ids}"
            )

    async def _reap_stale_tasks(self) -> None:
        """Periodic recovery of stuck rows (runs from the cleanup loop).

        (1) 'doing' rows older than 2x task_timeout are zombies: the worker
        enforces task_timeout on every execution, so no legitimate run can
        last that long — either the finalize write failed or the owning
        process died mid-run. They are marked 'failed' (TaskReaped) rather
        than re-enqueued: a failed cron task unblocks the scheduler dedup
        (next matching tick re-creates it) and a re-run loop on a task that
        crashes its process is avoided.

        (2) 'enqueued' children whose parent ended failed/cancelled can never
        be claimed (the claim SQL requires the parent to be 'done'): cascade
        the parent's terminal state to the whole subtree.
        """
        from sqlalchemy import text

        # (1) Timeout-stale 'doing' rows → failed (TaskReaped)
        stale_after = max(int(self.config.task_timeout or 0), 1) * 2
        # stale_after is a Python-computed int: safe to interpolate in the
        # message (binding it there would be typed as text by Postgres and
        # rejected by asyncpg for an int value).
        sql = text(
            "UPDATE queued_tasks "
            "SET state = 'failed'::queuedtaskstate, "
            "    exception_name = 'TaskReaped', "
            f"    exception_message = 'Task stuck in doing state for more than {stale_after}s, reaped', "
            "    date_failed = NOW(), date_ended = NOW(), "
            "    execution_time = EXTRACT(EPOCH FROM (NOW() - COALESCE(date_started, NOW()))), "
            "    updated_at = NOW() "
            "WHERE state = 'doing'::queuedtaskstate "
            "  AND date_started < NOW() - make_interval(secs => :stale_after) "
            "RETURNING id"
        )
        rows = await self.database.fetch_all(sql, {"stale_after": stale_after})
        if rows:
            ids = [row[0] for row in rows]
            logger.warning(
                f"Reaped {len(ids)} stale 'doing' task(s) (older than {stale_after}s): {ids}"
            )

        # (2) 'enqueued' children of terminally-failed parents → cascade
        orphan_sql = text(
            "SELECT c.id, p.id, p.state, p.name "
            "FROM queued_tasks c "
            "JOIN queued_tasks p ON p.id = c.parent_task "
            "WHERE c.state = 'enqueued'::queuedtaskstate "
            "  AND p.state IN ('failed'::queuedtaskstate, 'cancelled'::queuedtaskstate)"
        )
        orphans = await self.database.fetch_all(orphan_sql)
        for row in orphans:
            child_id, parent_id, parent_state, parent_name = (
                row[0],
                row[1],
                str(row[2]),
                row[3],
            )
            if parent_state == QueuedTaskState.failed.name:
                new_state = QueuedTaskState.failed
                exception_name: Optional[str] = "ParentTaskFailed"
                exception_message: Optional[str] = f"Parent task {parent_id} failed"
                exception_info: Optional[str] = (
                    f"Parent task '{parent_name}' failed, cascading to descendants"
                )
            else:
                new_state = QueuedTaskState.cancelled
                exception_name = None
                exception_message = None
                exception_info = None

            try:
                cascaded = await self._cascade_to_descendants(
                    root_task_id=child_id,
                    new_state=new_state,
                    exception_name=exception_name,
                    exception_message=exception_message,
                    exception_info=exception_info,
                )
                logger.warning(
                    f"Cascaded {parent_state} from parent {parent_id} to "
                    f"{cascaded} stuck descendant(s) (root {child_id})"
                )
            except Exception as e:
                logger.error(
                    f"Error cascading {parent_state} from parent {parent_id} "
                    f"to descendants (root {child_id}): {e}"
                )

    async def _cascade_to_descendants(
        self,
        root_task_id: int,
        new_state: QueuedTaskState,
        exception_name: Optional[str] = None,
        exception_message: Optional[str] = None,
        exception_info: Optional[str] = None,
        max_depth: int = 100,
    ) -> int:
        """
        Atomically mark a task AND all of its descendants with a terminal
        state via a single recursive CTE UPDATE.

        Replaces the previous N+1 + Python-recursive implementation which:
        - issued one SELECT per tree level and one full-row UPDATE
          (.save()) per node — clobbering columns concurrently written
          by workers and generating "could not serialize access due to
          concurrent update" noise on every collision,
        - had no cap and would recurse forever on a cycle in the
          parent_task graph,
        - was not atomic across the tree (mid-cascade crash left the
          subtree in an inconsistent half-failed state).

        The recursive CTE walks the subtree server-side; the UPDATE
        targets only rows still in (enqueued, doing), so terminal
        states set by another path (worker finalization, graceful
        shutdown) are preserved. A depth cap protects against accidental
        cycles.

        Args:
            root_task_id: Anchor of the cascade (root itself is included).
            new_state: Must be QueuedTaskState.failed or .cancelled.
            exception_*: Only meaningful for 'failed' (uses COALESCE so
                None doesn't overwrite existing values).
            max_depth: Hard recursion cap — beyond this descendants are
                silently skipped.

        Returns:
            Number of rows actually updated (root included).
        """
        if new_state not in (QueuedTaskState.failed, QueuedTaskState.cancelled):
            raise ValueError(
                f"_cascade_to_descendants requires failed or cancelled, "
                f"got {new_state}"
            )

        from sqlalchemy import text

        sql = text(
            "WITH RECURSIVE descendants(id, depth) AS (\n"
            "  SELECT id, 0 FROM queued_tasks WHERE id = :root_id\n"
            "  UNION ALL\n"
            "  SELECT c.id, d.depth + 1\n"
            "  FROM queued_tasks c\n"
            "  INNER JOIN descendants d ON c.parent_task = d.id\n"
            "  WHERE d.depth < :max_depth\n"
            ")\n"
            "UPDATE queued_tasks t\n"
            "SET state = :new_state::queuedtaskstate,\n"
            "    date_failed    = CASE WHEN :new_state = 'failed'    THEN NOW() ELSE date_failed    END,\n"
            "    date_cancelled = CASE WHEN :new_state = 'cancelled' THEN NOW() ELSE date_cancelled END,\n"
            "    date_ended     = NOW(),\n"
            "    exception_name    = COALESCE(:exception_name,    exception_name),\n"
            "    exception_message = COALESCE(:exception_message, exception_message),\n"
            "    exception_info    = COALESCE(:exception_info,    exception_info),\n"
            "    updated_at = NOW()\n"
            "FROM descendants d\n"
            "WHERE t.id = d.id\n"
            "  AND t.state IN ('enqueued'::queuedtaskstate, 'doing'::queuedtaskstate)\n"
            "RETURNING t.id"
        )

        rows = await self.database.fetch_all(
            sql,
            {
                "root_id": root_task_id,
                "new_state": new_state.name,
                "exception_name": exception_name,
                "exception_message": exception_message,
                "exception_info": exception_info,
                "max_depth": max_depth,
            },
        )
        return len(rows)

    async def _init_db(self) -> None:
        """
        Initialize database with required triggers for queue system

        Creates PostgreSQL trigger for NOTIFY/LISTEN if not exists,
        updates if different, does nothing if up to date.
        """

        # PostgreSQL function for notifications (use configured channel)
        channel = self.config.notify_channel.replace("'", "''")
        function_sql = f"""
            CREATE OR REPLACE FUNCTION notify_new_queued_task()
            RETURNS TRIGGER AS $$
            BEGIN
                -- Only notify for enqueued tasks
                IF NEW.state = 'enqueued' THEN
                    PERFORM pg_notify('{channel}',
                        json_build_object(
                            'task_id', NEW.id,
                            'state', NEW.state,
                            'module_name', NEW.module_name,
                            'function_name', NEW.function_name,
                            'created_at', NEW.created_at
                        )::text
                    );
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql; \
        """

        # PostgreSQL trigger - separate commands
        drop_trigger_sql = "DROP TRIGGER IF EXISTS queued_task_notify ON queued_tasks;"
        create_trigger_sql = """
                             CREATE TRIGGER queued_task_notify
                                 AFTER INSERT OR
                             UPDATE ON queued_tasks
                                 FOR EACH ROW
                                 EXECUTE FUNCTION notify_new_queued_task(); \
                             """

        async with self.database.transaction():
            # Create/update function
            await self.database.execute(function_sql)

            # Drop existing trigger
            await self.database.execute(drop_trigger_sql)

            # Create new trigger
            await self.database.execute(create_trigger_sql)

            logger.info("PostgreSQL triggers for queue system initialized successfully")

    async def _execute_task_with_worker(self, worker, task: "QueuedTask") -> None:
        """
        Execute a task with a worker and handle completion

        Args:
            worker: QueueWorker instance
            task: QueuedTask to execute
        """
        try:
            # Execute the task
            result = await worker.run_task(task)

            if result["status"] == "success":
                self.stats["tasks_processed"] += 1
                logger.info(f"Task {task.id} completed by worker {worker.worker_id}")
            else:
                self.stats["tasks_failed"] += 1
                logger.error(
                    f"Task {task.id} failed in worker {worker.worker_id}: {result.get('error')}"
                )

        except Exception as e:
            self.stats["tasks_failed"] += 1
            logger.error(f"Unexpected error executing task {task.id}: {e}")

        finally:
            # Return worker to pool
            await self.worker_pool.return_worker(worker)
            # Immediately try to claim next tasks to keep workers busy
            if self.is_running:
                asyncio.create_task(self._process_pending_tasks())

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive manager statistics"""
        worker_stats = await self.worker_pool.get_pool_stats()

        uptime = None
        if self.stats["started_at"]:
            uptime = (
                datetime.now(context.get_timezone()) - self.stats["started_at"]
            ).total_seconds()

        return {
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "max_workers": self.max_workers,
            "worker_pool": worker_stats,
            "tasks_processed": self.stats["tasks_processed"],
            "tasks_failed": self.stats["tasks_failed"],
            "notifications_received": self.stats["notifications_received"],
            "polling_cycles": self.stats["polling_cycles"],
            "config": {
                "use_postgresql_notify": self.config.use_postgresql_notify,
                "polling_interval": self.config.polling_interval,
                "fallback_polling_interval": self.config.fallback_polling_interval,
                "worker_idle_timeout": self.config.worker_idle_timeout,
            },
        }

    async def _register_server(self) -> None:
        """Register this server in the database"""

        QueuedTaskWorker = cast(
            type["QueuedTaskWorker"],
            self.registry.get_model("QueuedTaskWorker"),
        )
        try:
            # Try to get existing record for this server
            self.worker_status_record = await QueuedTaskWorker.query.filter(
                QueuedTaskWorker.columns.server_name == self.server_name
            ).get_or_none()

            if self.worker_status_record:
                # Update existing record
                self.worker_status_record.mark_as_started(self.max_workers)
                await self.worker_status_record.save()
            else:
                # Create new record
                queued_task_worker = QueuedTaskWorker(  # type: ignore
                    server_name=self.server_name,
                    max_workers=self.max_workers,
                    is_running=True,
                    started_at=datetime.now(context.get_timezone()),
                    last_heartbeat=datetime.now(context.get_timezone()),
                )
                await queued_task_worker.save()
                self.worker_status_record = queued_task_worker

            logger.info(f"Server '{self.server_name}' registered in database")

        except Exception as e:
            logger.error(f"Failed to register server in database: {e}")
            raise

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            if not self.shutdown_event.is_set():
                self.shutdown_event.set()

        # Setup handlers for SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.debug("Signal handlers setup for graceful shutdown")

    async def _unregister_server(self) -> None:
        """Mark server as stopped in database"""
        if self.worker_status_record:
            try:
                self.worker_status_record.mark_as_stopped()
                await self.worker_status_record.save()
                logger.info(f"Server '{self.server_name}' marked as stopped")
            except Exception as e:
                logger.error(f"Failed to unregister server: {e}")

    async def _heartbeat_task(self) -> None:
        """Periodic heartbeat to update server status in database"""
        logger.info("Starting heartbeat task (30s interval)")

        while self.is_running:
            try:
                await asyncio.sleep(30)  # Heartbeat every 30 seconds

                if self.is_running and self.worker_status_record:
                    # Update worker statistics
                    busy_workers = len(self.worker_pool.busy_workers)
                    idle_workers = self.worker_pool.idle_workers.qsize()

                    self.worker_status_record.update_stats(
                        active=busy_workers, idle=idle_workers, is_running=True
                    )
                    await self.worker_status_record.save()

                    logger.debug(
                        f"Heartbeat: {busy_workers} active, {idle_workers} idle workers"
                    )

            except asyncio.CancelledError:
                logger.debug("Heartbeat task cancelled")
                break
            except Exception as e:
                logger.error(f"Heartbeat task error: {e}")

    @classmethod
    async def get_global_stats(cls) -> Dict[str, Any]:
        """Get global statistics across all servers"""
        try:
            # Get all alive AND running servers (heartbeat within last 2 minutes and is_running=True)
            registry = get_service(Registry)
            QueuedTaskWorker = cast(
                type["QueuedTaskWorker"],
                registry.get_model("QueuedTaskWorker"),
            )
            alive_servers = await QueuedTaskWorker.query.filter(
                QueuedTaskWorker.columns.last_heartbeat
                >= datetime.now(context.get_timezone()) - timedelta(minutes=2),
                QueuedTaskWorker.columns.is_running == True,
            ).all()

            total_servers = len(alive_servers)
            total_max_workers = sum(server.max_workers for server in alive_servers)
            total_active_workers = sum(
                server.active_workers for server in alive_servers
            )
            total_idle_workers = sum(server.idle_workers for server in alive_servers)

            return {
                "servers": total_servers,
                "max_workers": total_max_workers,
                "active_workers": total_active_workers,
                "idle_workers": total_idle_workers,
                "total_workers": total_active_workers + total_idle_workers,
                "servers_detail": [
                    {
                        "server_name": server.server_name,
                        "max_workers": server.max_workers,
                        "active_workers": server.active_workers,
                        "idle_workers": server.idle_workers,
                        "is_running": server.is_running,
                        "started_at": server.started_at,
                        "last_heartbeat": server.last_heartbeat,
                    }
                    for server in alive_servers
                ],
            }

        except Exception as e:
            logger.error(f"Failed to get global stats: {e}")
            return {
                "servers": 0,
                "max_workers": 0,
                "active_workers": 0,
                "idle_workers": 0,
                "total_workers": 0,
                "servers_detail": [],
            }
