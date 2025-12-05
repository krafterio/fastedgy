# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TYPE_CHECKING, cast

from fastedgy.orm import Registry
from fastedgy.queued_task.models.queued_task import QueuedTaskState

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask

logger = logging.getLogger("scheduler")


class Scheduler:
    """
    Service to schedule tasks for future execution using QueuedTasks.
    """

    def __init__(self, registry: Registry):
        self.registry = registry

    async def schedule(
        self,
        func: Callable | str,
        run_at: datetime | timedelta,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> "QueuedTask":
        """
        Schedule a task for future execution.

        Args:
            func: Function to execute or string 'module_name.function_name'
            run_at: Datetime for execution OR timedelta (delay from now)
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            context: Optional context dictionary
            name: Optional name for the task

        Returns:
            The created QueuedTask instance
        """
        # Calculate execution date
        if isinstance(run_at, timedelta):
            date_enqueued = datetime.now(timezone.utc) + run_at
        else:
            # Ensure timezone awareness if possible, or assume UTC if naive
            if run_at.tzinfo is None:
                date_enqueued = run_at.replace(tzinfo=timezone.utc)
            else:
                date_enqueued = run_at

        # Resolve function name and module
        module_name = ""
        function_name = ""

        if isinstance(func, str):
            if "." not in func:
                raise ValueError(f"Function string must be in format 'module.function', got '{func}'")
            module_name, function_name = func.rsplit(".", 1)
        else:
            if not hasattr(func, "__module__") or not hasattr(func, "__name__"):
                raise ValueError("Callable must have __module__ and __name__ attributes")
            module_name = func.__module__
            function_name = func.__name__

        # Get the QueuedTask model dynamically to avoid circular imports
        QueuedTask = cast(
            type["QueuedTask"], self.registry.get_model("QueuedTask")
        )

        # Create the task
        task = await QueuedTask.query.create(
            name=name or f"Scheduled: {function_name}",
            module_name=module_name,
            function_name=function_name,
            args=args or [],
            kwargs=kwargs or {},
            context=context or {},
            date_enqueued=date_enqueued,
            state=QueuedTaskState.enqueued,
        )

        logger.info(f"Scheduled task {task.id} ({module_name}.{function_name}) for {date_enqueued}")

        return task

    async def cancel(self, task_id: int) -> bool:
        """
        Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if cancelled, False if not found or already done/failed
        """
        QueuedTask = cast(
            type["QueuedTask"], self.registry.get_model("QueuedTask")
        )

        task = await QueuedTask.query.get_or_none(id=task_id)
        if not task:
            return False

        if task.state in [QueuedTaskState.done, QueuedTaskState.failed, QueuedTaskState.cancelled]:
            return False

        task.mark_as_cancelled()
        await task.save()
        return True
