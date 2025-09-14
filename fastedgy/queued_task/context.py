# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio

from contextvars import ContextVar

from typing import Optional, TYPE_CHECKING, Any, Dict

from fastedgy.dependencies import get_service
from fastedgy.orm import Database

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


# Context variable to hold the current queues task
current_queued_task: ContextVar[Optional["QueuedTask"]] = ContextVar(
    "current_queued_task", default=None
)


# Context variable to hold the execution context (always available)
current_execution_context: ContextVar[Dict[str, Any]] = ContextVar(
    "current_execution_context", default={}
)


def get_current_task() -> Optional["QueuedTask"]:
    """Get the current queues task from context"""
    return current_queued_task.get()


def set_current_task(task: Optional["QueuedTask"]) -> None:
    """Set the current queues task in context"""
    current_queued_task.set(task)


def get_context(path: str, default: Any = None) -> Any:
    """
    Get a value from the execution context using nested path notation

    Args:
        path: Dot-separated path (e.g., 'user.profile.name')
        default: Default value if path doesn't exist

    Returns:
        The value at the specified path or default

    Examples:
        get_context('step')  # Returns current step
        get_context('user.profile.name', 'Unknown')  # Nested access
    """
    context = current_execution_context.get()

    if not context:
        return default

    paths = path.split(".")
    value = context

    for key in paths:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def set_context(path: str, value: Any, auto_commit: bool = True) -> None:
    """
    Set a value in the execution context using nested path notation

    Args:
        path: Dot-separated path (e.g., 'user.profile.name')
        value: Value to set
        auto_commit: If True, automatically save to database if QueuedTask is available

    Examples:
        set_context('step', 'validation')
        set_context('user.profile.name', 'John Doe')
        set_context('progress', 50, auto_commit=False)  # No DB save
    """
    # Get current context or create new one
    context = (
        current_execution_context.get().copy()
        if current_execution_context.get()
        else {}
    )

    # Navigate and create nested structure
    paths = path.split(".")
    nested_context = context

    # Create nested dictionaries for all but the last key
    for key in paths[:-1]:
        nested_context = nested_context.setdefault(key, {})

    # Set the final value
    nested_context[paths[-1]] = value

    # Update the context variable
    current_execution_context.set(context)

    # Auto-commit to database if requested and task is available
    if auto_commit:
        task = get_current_task()
        if task is not None:
            try:
                # Create async task for database update
                asyncio.create_task(_update_task_context_async(task, context))
            except RuntimeError:
                # No event loop available - skip database update silently
                pass


async def _update_task_context_async(
    task: "QueuedTask", context: Dict[str, Any]
) -> None:
    """Update task context in database asynchronously"""
    try:
        # Update the task context field
        db = get_service(Database)
        query = (
            task.__class__.query.table.update()
            .where(task.__class__.query.table.c.id == task.id)
            .values(context=context)
        )

        await db.execute(query)
        task.context = context
    except Exception as e:
        # Don't let database errors break the execution
        # Log to the queued task logger if available
        try:
            from fastedgy.queued_task.logging import getLogger

            logger = getLogger("queued_task.context")
            logger.error(f"Failed to update task context in database: {e}")
        except ImportError:
            # Fallback to standard logging
            import logging

            logging.getLogger("queued_task.context").error(
                f"Failed to update task context: {e}"
            )


def clear_context() -> None:
    """Clear the current execution context"""
    current_execution_context.set({})


def get_full_context() -> Dict[str, Any]:
    """Get the complete execution context as a dictionary"""
    return current_execution_context.get().copy()


def set_full_context(context: Dict[str, Any], auto_commit: bool = True) -> None:
    """
    Replace the entire execution context

    Args:
        context: New context dictionary
        auto_commit: If True, automatically save to database if QueuedTask is available
    """
    current_execution_context.set(context.copy())

    # Auto-commit to database if requested and task is available
    if auto_commit:
        task = get_current_task()
        if task is not None:
            try:
                # Create async task for database update
                asyncio.create_task(_update_task_context_async(task, context))
            except RuntimeError:
                # No event loop available - skip database update silently
                pass


class TaskContext:
    """Context manager for setting the current task and execution context"""

    def __init__(
        self,
        task: Optional["QueuedTask"],
        execution_context: Optional[Dict[str, Any]] = None,
    ):
        self.task = task
        self.execution_context = execution_context or (task.context if task else {})
        self.task_token = None
        self.context_token = None

    def __enter__(self):
        self.task_token = current_queued_task.set(self.task)
        self.context_token = current_execution_context.set(
            self.execution_context.copy()
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context_token is not None:
            current_execution_context.reset(self.context_token)
        if self.task_token is not None:
            current_queued_task.reset(self.task_token)
