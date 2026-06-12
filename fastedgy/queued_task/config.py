# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from edgy import Database, Registry


class QueuedTaskConfig:
    # Logging configuration
    enable_db_logging: bool = True
    enable_dual_logging: bool = True

    # Worker configuration
    max_workers: int = int(
        os.environ.get("QUEUED_TASK_MAX_WORKERS", os.cpu_count() or 1)
    )
    worker_idle_timeout: int = int(
        os.environ.get("QUEUED_TASK_WORKER_IDLE_TIMEOUT", 60)
    )  # seconds

    # Manager configuration
    polling_interval: int = int(
        os.environ.get("QUEUED_TASK_POLLING_INTERVAL", 2)
    )  # seconds
    fallback_polling_interval: int = int(
        os.environ.get("QUEUED_TASK_FALLBACK_POLLING_INTERVAL", 30)
    )  # seconds

    # Task execution configuration
    task_timeout: int = int(
        os.environ.get("QUEUED_TASK_TIMEOUT", 300)
    )  # 5 minutes default
    max_retries: int = int(os.environ.get("QUEUED_TASK_MAX_RETRIES", 3))

    # Notification configuration
    use_postgresql_notify: bool = bool(
        os.environ.get("QUEUED_TASK_USE_POSTGRESQL_NOTIFY", "true").lower() == "true"
    )
    notify_channel: str = os.environ.get(
        "QUEUED_TASK_NOTIFY_CHANNEL", "queued_new_task"
    )

    # Dedicated manager DB pool sizing (bookkeeping writes: task states, logs,
    # heartbeat). Kept small and explicit — without it the pool would silently
    # fall back to SQLAlchemy defaults, ungoverned by any app configuration.
    manager_db_pool_size: int = int(
        os.environ.get("QUEUED_TASK_MANAGER_DB_POOL_SIZE", 5)
    )
    manager_db_max_overflow: int = int(
        os.environ.get("QUEUED_TASK_MANAGER_DB_MAX_OVERFLOW", 5)
    )

    # Liveness file for container healthchecks, touched by the manager
    # heartbeat every 30s (empty disables). Signals event-loop liveness only,
    # deliberately not DB health.
    health_file: str = os.environ.get("QUEUED_TASK_HEALTH_FILE", "")

    # Retention window (days) for terminal tasks (done/failed/cancelled/
    # stopped) kept in queued_tasks: past it the manager purges them hourly
    # (their queued_task_logs rows follow via ON DELETE CASCADE). Failed
    # tasks therefore stay inspectable/retryable within the window. 0
    # disables purging entirely.
    retention_days: int = int(os.environ.get("QUEUED_TASK_RETENTION_DAYS", 30))

    # Manager registry (dedicated database connection for queue management operations)
    _manager_registry: Optional["Registry"] = None
    _manager_database: Optional["Database"] = None

    async def init_manager_registry(self) -> "Registry":
        """
        Initialize the dedicated manager registry with its own database connection.

        This registry is used for queue management operations (logging, task state updates)
        to avoid transaction conflicts with the main application database operations.

        Must be called during worker startup (e.g., in QueueWorkerManager.start_workers).
        """
        if self._manager_registry is not None:
            return self._manager_registry

        from edgy import Database, Registry
        from fastedgy.dependencies import get_service
        from fastedgy.orm import Registry as MainRegistry

        # Get main registry to access database URL and models
        main_registry = get_service(MainRegistry)

        # Create dedicated database connection (same URL, separate connection
        # pool, explicitly sized)
        self._manager_database = Database(
            str(main_registry.database.url),
            pool_size=self.manager_db_pool_size,
            max_overflow=self.manager_db_max_overflow,
        )
        await self._manager_database.connect()

        # Create dedicated registry with the new database
        self._manager_registry = Registry(database=self._manager_database)

        # Copy queued task models to the manager registry
        for model_name in ("QueuedTask", "QueuedTaskLog", "QueuedTaskWorker"):
            try:
                model = main_registry.get_model(model_name)
                model.copy_edgy_model(
                    registry=self._manager_registry, on_conflict="replace"
                )
            except LookupError:
                # Model not found in main registry, skip
                pass

        return self._manager_registry

    def get_manager_registry(self) -> Optional["Registry"]:
        """
        Get the manager registry if initialized.

        Returns None if init_manager_registry() has not been called yet.
        For async initialization, use init_manager_registry() instead.
        """
        return self._manager_registry

    async def close_manager_registry(self) -> None:
        """
        Close the manager database connection and cleanup.

        Should be called during worker shutdown (e.g., in QueueWorkerManager.stop_workers).
        """
        if self._manager_database is not None:
            try:
                await self._manager_database.disconnect()
            finally:
                # Always reset, even when disconnect fails: a stale half-closed
                # registry must never be reused by a later start.
                self._manager_database = None
                self._manager_registry = None
        else:
            self._manager_registry = None
