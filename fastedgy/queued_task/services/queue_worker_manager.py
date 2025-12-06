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
        self.shutdown_event = asyncio.Event()

        # Statistics
        self.stats = {
            "started_at": None,
            "tasks_processed": 0,
            "tasks_failed": 0,
            "notifications_received": 0,
            "polling_cycles": 0,
        }

    async def start_workers(self, max_workers: Optional[int] = None) -> None:
        """
        Start the worker manager system

        Args:
            max_workers: Override max workers for this session
        """
        if self.is_running:
            logger.warning("Worker manager is already running")
            return

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

        # Register this server in the database
        await self._register_server()

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
        """Periodic cleanup of idle workers and stats logging"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Check every minute

                if self.is_running:
                    stats = await self.get_stats()
                    logger.debug(f"Worker stats: {stats['worker_pool']}")

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

            # Load the task model instance
            QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
            task = await QueuedTask.query.filter(
                QueuedTask.columns.id == claimed_id
            ).get_or_none()
            return task
        except Exception as e:
            logger.error(f"Error claiming next ready task: {e}")
            return None

    async def _get_next_ready_task(self) -> Optional["QueuedTask"]:
        """
        Get the NEXT task that is ready to be processed:
        - State = enqueued
        - No parent_task OR parent_task.state = done
        - Returns only ONE task to avoid race conditions
        """
        QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
        try:
            # Get enqueued tasks one by one, ordered by priority
            enqueued_tasks = (
                await QueuedTask.query.filter(
                    QueuedTask.columns.state == QueuedTaskState.enqueued
                )
                .order_by("date_enqueued")
                .all()
            )

            for task in enqueued_tasks:
                if task.parent_task is None:
                    # No parent, task is ready
                    logger.debug(f"Task {task.id} ready (no parent)")
                    return task
                else:
                    # Check parent state
                    parent = await QueuedTask.query.filter(
                        QueuedTask.columns.id == task.parent_task.id
                    ).get_or_none()

                    if parent and parent.state == QueuedTaskState.done:
                        # Parent is done, task is ready
                        logger.debug(
                            f"Task {task.id} ready (parent {parent.id} is done)"
                        )
                        return task
                    elif parent and parent.state in [
                        QueuedTaskState.failed,
                        QueuedTaskState.cancelled,
                    ]:
                        # Parent failed/cancelled, cascade to child
                        logger.info(
                            f"Task {task.id} cascading failure from parent {parent.id} ({parent.state})"
                        )
                        await self._cascade_parent_failure(task, parent)
                        # Continue to next task (this one is now failed)
                        continue
                    else:
                        # Parent not ready, task must wait
                        parent_state = parent.state if parent else "not_found"
                        logger.debug(
                            f"Task {task.id} waiting (parent {task.parent_task.id} is {parent_state})"
                        )
                        # Continue to next task
                        continue

            # No ready tasks found
            return None

        except Exception as e:
            logger.error(f"Error getting next ready task: {e}")
            return None

    async def _get_ready_tasks(self) -> List["QueuedTask"]:
        """
        Get tasks that are ready to be processed in parallel:
        - State = enqueued
        - No parent_task OR parent_task.state = done
        - Uses atomic checks to avoid race conditions
        """
        QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
        try:
            # Get all enqueued tasks ordered by priority (date_enqueued)
            enqueued_tasks = (
                await QueuedTask.query.filter(
                    QueuedTask.columns.state == QueuedTaskState.enqueued
                )
                .order_by("date_enqueued")
                .all()
            )

            ready_tasks = []
            processed_parent_ids = set()  # Track parents we've already checked

            for task in enqueued_tasks:
                # Skip if we're already processing tasks with this parent
                # This prevents race conditions where multiple children of the same parent
                # are assigned before the parent state can be updated
                if task.parent_task and task.parent_task.id in processed_parent_ids:
                    logger.debug(
                        f"Task {task.id} skipped (parent {task.parent_task.id} already being processed)"
                    )
                    continue

                if task.parent_task is None:
                    # No parent, task is ready
                    logger.debug(f"Task {task.id} ready (no parent)")
                    ready_tasks.append(task)
                else:
                    # Check parent state atomically
                    parent = await QueuedTask.query.filter(
                        QueuedTask.columns.id == task.parent_task.id
                    ).get_or_none()

                    if parent and parent.state == QueuedTaskState.done:
                        # Parent is done, task is ready
                        logger.debug(
                            f"Task {task.id} ready (parent {parent.id} is done)"
                        )
                        ready_tasks.append(task)
                        # Mark this parent as processed so siblings can also be included
                        processed_parent_ids.add(parent.id)
                    elif parent and parent.state in [
                        QueuedTaskState.failed,
                        QueuedTaskState.cancelled,
                    ]:
                        # Parent failed/cancelled, cascade to child
                        logger.info(
                            f"Task {task.id} cascading failure from parent {parent.id} ({parent.state})"
                        )
                        await self._cascade_parent_failure(task, parent)
                        # Don't add to ready_tasks, this task is now failed
                    else:
                        # Parent not ready (enqueued, doing, etc.), task must wait
                        parent_state = parent.state if parent else "not_found"
                        logger.debug(
                            f"Task {task.id} waiting (parent {task.parent_task.id} is {parent_state})"
                        )

            logger.debug(
                f"Found {len(ready_tasks)} ready tasks out of {len(enqueued_tasks)} enqueued"
            )
            return ready_tasks

        except Exception as e:
            logger.error(f"Error getting ready tasks: {e}")
            return []

    async def _cascade_parent_failure(
        self, child_task: "QueuedTask", parent_task: "QueuedTask"
    ) -> None:
        """
        Cascade parent failure to child tasks
        """
        try:
            if parent_task.state == QueuedTaskState.failed:
                child_task.mark_as_failed(
                    exception_name="ParentTaskFailed",
                    exception_message=f"Parent task {parent_task.id} failed",
                    exception_info=f"Parent task '{parent_task.name}' failed, cascading to child",
                )
            elif parent_task.state == QueuedTaskState.cancelled:
                child_task.mark_as_cancelled()

            await child_task.save()
            logger.info(
                f"Cascaded parent {parent_task.state} to child task {child_task.id}"
            )

            # Recursively cascade to grandchildren
            await self._cascade_to_children(child_task)

        except Exception as e:
            logger.error(f"Error cascading parent failure: {e}")

    async def _cascade_to_children(self, parent_task: "QueuedTask") -> None:
        """
        Recursively cascade task state to all children
        """
        QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))
        try:
            children = await QueuedTask.query.filter(
                QueuedTask.columns.parent_task == parent_task.id
            ).all()

            for child in children:
                # Cascade to children that are enqueued OR doing
                if child.state in [QueuedTaskState.enqueued, QueuedTaskState.doing]:
                    if parent_task.state == QueuedTaskState.failed:
                        child.mark_as_failed(
                            exception_name="ParentTaskFailed",
                            exception_message=f"Parent task {parent_task.id} failed",
                            exception_info=f"Parent task '{parent_task.name}' failed, cascading to child",
                        )
                    elif parent_task.state == QueuedTaskState.cancelled:
                        child.mark_as_cancelled()

                    await child.save()
                    logger.info(
                        f"Cascaded {parent_task.state} to child task {child.id} (was {child.state})"
                    )

                    # If child was doing, we should ideally signal the worker to stop
                    # For now, the worker will complete but the final state will be overridden

                    # Recursive cascade to grandchildren
                    await self._cascade_to_children(child)

        except Exception as e:
            logger.error(f"Error cascading to children: {e}")

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
