# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, TYPE_CHECKING

from fastedgy import context as fastedgy_context
from fastedgy.dependencies import get_service
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
        auto_remove: bool = True,
    ) -> "QueuedTask":
        """
        Schedule a task for future execution.

        Args:
            func: Function to execute or string 'module_name.function_name'
            run_at: Datetime for execution OR timedelta (delay from now)
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            context: Optional context dictionary (overrides hook-provided context keys)
            name: Optional name for the task
            auto_remove: Auto-remove task after successful execution

        Returns:
            The created QueuedTask instance
        """
        # Calculate execution date
        if isinstance(run_at, timedelta):
            date_enqueued = datetime.now(fastedgy_context.get_timezone()) + run_at
        else:
            date_enqueued = run_at

        # Resolve function name and module
        module_name = ""
        function_name = ""

        if isinstance(func, str):
            if "." not in func:
                raise ValueError(
                    f"Function string must be in format 'module.function', got '{func}'"
                )
            module_name, function_name = func.rsplit(".", 1)
        else:
            if not hasattr(func, "__module__") or not hasattr(func, "__name__"):
                raise ValueError(
                    "Callable must have __module__ and __name__ attributes"
                )
            module_name = func.__module__
            function_name = func.__name__

        # Use QueuedTasks service to create task with proper hooks
        from fastedgy.queued_task.services.queued_tasks import QueuedTasks

        queued_tasks = get_service(QueuedTasks)
        task = await queued_tasks.create_task(
            module_name=module_name,
            function_name=function_name,
            args=args or [],
            kwargs=kwargs or {},
            context=context or {},
            name=name or f"Scheduled: {function_name}",
            auto_remove=auto_remove,
            date_enqueued=date_enqueued,
        )

        logger.info(
            f"Scheduled task {task.id} ({module_name}.{function_name}) for {date_enqueued}"
        )

        return task

    async def cancel(self, task_id: int) -> bool:
        """
        Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if cancelled, False if not found or already done/failed
        """
        from typing import cast

        QueuedTask = cast(type["QueuedTask"], self.registry.get_model("QueuedTask"))

        task = await QueuedTask.query.get_or_none(id=task_id)
        if not task:
            return False

        if task.state in [
            QueuedTaskState.done,
            QueuedTaskState.failed,
            QueuedTaskState.cancelled,
        ]:
            return False

        if task.state == QueuedTaskState.enqueued:
            await task.delete()
            return True

        task.mark_as_cancelled()
        await task.save()
        return True
