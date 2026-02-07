# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, Callable, Dict, Optional

import rich_click as click

from fastedgy.dependencies import get_service
from fastedgy.queued_task.scheduler.registry import (
    ScheduledTaskRegistry,
    ScheduledTaskDef,
)


class Option(click.Option):
    """Custom Option subclass for scheduled tasks.

    Currently identical to click.Option but provides an extension point
    for future scheduler-specific option behavior.
    """

    pass


def option(*param_decls: str, **attrs: Any) -> Callable:
    """Decorator to add an option to a scheduled task.

    Wraps click.option but uses the scheduler-specific Option class.
    Must be applied BEFORE @scheduled_task in decorator order (i.e., below it),
    so that it runs first and attaches option metadata to the function.

    Usage:
        @scheduled_task(name="my-task", cron="0 8 * * *")
        @option("--date", type=str, default=None, help="Target date")
        async def my_task(date: str | None = None):
            ...
    """
    cls = attrs.pop("cls", Option)

    def decorator(func: Callable) -> Callable:
        if not hasattr(func, "_scheduled_task_options"):
            func._scheduled_task_options = []

        opt = cls(param_decls, **attrs)
        func._scheduled_task_options.insert(0, opt)
        return func

    return decorator


def scheduled_task(
    cron: str,
    name: Optional[str] = None,
    description: str = "",
    auto_remove: bool = True,
    enabled: bool = True,
    context: Optional[Dict[str, Any]] = None,
) -> Callable:
    """Decorator to register a function as a cron-scheduled task.

    The decorated function will be:
    1. Registered in the ScheduledTaskRegistry for CronScheduler to discover
    2. Auto-exposed as a CLI command under ``kt scheduler <name>``
    3. Executed by a queue worker when the cron fires

    The function signature should accept keyword arguments matching the defined
    options. It should NOT accept ctx/CliContext -- the worker handles lifespan.
    Use get_service() to access services.

    Usage:
        @scheduled_task(name="notify-birthday", cron="0 8 * * *", description="...")
        @option("--date", type=str, default=None, help="Target date")
        async def notify_birthday(date: str | None = None):
            push_service = get_service(PushNotification)
            ...
    """

    def decorator(func: Callable) -> Callable:
        options = getattr(func, "_scheduled_task_options", [])

        resolved_name = name or func.__name__.replace("_", "-").lower()

        task_def = ScheduledTaskDef(
            name=resolved_name,
            cron=cron,
            func=func,
            description=description or func.__doc__ or "",
            options=list(options),
            auto_remove=auto_remove,
            enabled=enabled,
            context=context,
        )

        registry = get_service(ScheduledTaskRegistry)
        registry.register(task_def)

        func._scheduled_task_def = task_def

        return func

    return decorator
