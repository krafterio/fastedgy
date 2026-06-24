# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from typing import TYPE_CHECKING, Optional, cast

if TYPE_CHECKING:
    from edgy import Database, Registry
    from fastedgy.orm import Model


def _parse_channel_capacities(raw: str) -> dict[str, int]:
    """Parse the QUEUED_TASK_CHANNELS env value ("sync:2,realtime:4").

    Raises ValueError on a malformed entry — failing fast at import beats a
    queue silently running without its capacity limits.
    """
    capacities: dict[str, int] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, capacity = entry.partition(":")
        name = name.strip()
        if not sep or not name:
            raise ValueError(f"Invalid QUEUED_TASK_CHANNELS entry '{entry}' (expected 'name:capacity')")
        try:
            value = int(capacity.strip())
        except ValueError:
            raise ValueError(
                f"Invalid QUEUED_TASK_CHANNELS capacity for channel "
                f"'{name}': '{capacity.strip()}' (expected an integer)"
            ) from None
        if value < 0:
            raise ValueError(
                f"Invalid QUEUED_TASK_CHANNELS capacity for channel '{name}': must be >= 0 (0 pauses the channel)"
            )
        capacities[name] = value
    return capacities


class QueuedTaskConfig:
    # Logging configuration
    enable_db_logging: bool = True
    enable_dual_logging: bool = True

    # Worker configuration
    max_workers: int = int(os.environ.get("QUEUED_TASK_MAX_WORKERS", os.cpu_count() or 1))
    worker_idle_timeout: int = int(os.environ.get("QUEUED_TASK_WORKER_IDLE_TIMEOUT", 60))  # seconds

    # Manager configuration
    polling_interval: int = int(os.environ.get("QUEUED_TASK_POLLING_INTERVAL", 2))  # seconds
    fallback_polling_interval: int = int(os.environ.get("QUEUED_TASK_FALLBACK_POLLING_INTERVAL", 30))  # seconds

    # Task execution configuration
    task_timeout: int = int(os.environ.get("QUEUED_TASK_TIMEOUT", 300))  # 5 minutes default

    # Bounded auto-retry budget: a task whose run fails is re-enqueued with
    # an exponential delay (30s, 2min, 8min, capped at 30min) until
    # retry_count reaches the budget, then fails terminally. Applies to
    # worker-side failures and reaped tasks (TaskReaped); TaskTimeoutError is
    # granted a single retry regardless (each attempt burns task_timeout
    # seconds of a worker slot). Cancelled/stopped tasks are never retried.
    # Per-task override via add_task(..., max_retries=N); 0 disables.
    max_retries: int = int(os.environ.get("QUEUED_TASK_MAX_RETRIES", 3))

    # Per-channel concurrency capacities ("sync:2,realtime:4"). A channel is
    # a concurrency cap, not a dedicated worker pool: the shared workers
    # simply never claim a task whose channel is already running `capacity`
    # tasks ON THIS CONTAINER (counting is per manager — with N replicas the
    # effective cap is N x capacity). Channels absent from the mapping are
    # unbounded (limited by the worker count); capacity 0 pauses a channel
    # (its tasks stay enqueued). Priority orders globally across channels.
    channels: dict[str, int] = _parse_channel_capacities(os.environ.get("QUEUED_TASK_CHANNELS", ""))

    # Notification configuration
    use_postgresql_notify: bool = bool(os.environ.get("QUEUED_TASK_USE_POSTGRESQL_NOTIFY", "true").lower() == "true")
    notify_channel: str = os.environ.get("QUEUED_TASK_NOTIFY_CHANNEL", "queued_new_task")

    # Dedicated manager DB pool sizing (bookkeeping writes: task states, logs,
    # heartbeat). Kept small and explicit — without it the pool would silently
    # fall back to SQLAlchemy defaults, ungoverned by any app configuration.
    manager_db_pool_size: int = int(os.environ.get("QUEUED_TASK_MANAGER_DB_POOL_SIZE", 5))
    manager_db_max_overflow: int = int(os.environ.get("QUEUED_TASK_MANAGER_DB_MAX_OVERFLOW", 5))

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
                cast("type[Model]", model).copy_edgy_model(registry=self._manager_registry, on_conflict="replace")
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
