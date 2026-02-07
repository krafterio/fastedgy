# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
from typing import Any

import rich_click as click

from fastedgy.dependencies import get_service
from fastedgy.queued_task.scheduler.registry import (
    ScheduledTaskRegistry,
    ScheduledTaskDef,
)


logger = logging.getLogger("queued_task.scheduler")


def create_scheduler_cli_group() -> click.Group:
    """Create the 'scheduler' CLI group with auto-generated commands.

    Each registered scheduled task becomes a subcommand:
        kt scheduler notify-birthday --date 2024-01-15

    The Click group's native listing (``kt scheduler --help``) shows all tasks.
    """
    from fastedgy.cli import (
        Group,
        Command,
        initialize_app,
        pass_cli_context,
        CliContext,
    )

    @click.group(name="scheduler", cls=Group)
    def scheduler_group():
        """Scheduled task commands."""
        pass

    registry = get_service(ScheduledTaskRegistry)

    for name, task_def in registry.get_all().items():
        cmd = _build_command_for_task(task_def)
        scheduler_group.add_command(cmd, name=name)

    scheduler_group.add_command(_build_status_command())

    return scheduler_group


def _build_status_command() -> click.Command:
    """Build the ``kt scheduler status`` command."""
    from fastedgy.cli import (
        Command,
        Table,
        console,
    )

    def status_callback():
        from datetime import datetime
        from cronsim import CronSim

        registry = get_service(ScheduledTaskRegistry)

        table = Table(title="Scheduled Tasks")
        table.add_column("Name", style="cyan")
        table.add_column("Enabled", style="green")
        table.add_column("Cron", style="yellow")
        table.add_column("Schedule", style="white")

        now = datetime.now()

        for name, task_def in registry.get_all().items():
            enabled = registry.is_task_enabled(name)
            enabled_str = "Yes" if enabled else "No"
            enabled_style = "green" if enabled else "red"

            try:
                schedule = CronSim(task_def.cron, now).explain()
            except Exception:
                schedule = ""

            table.add_row(
                name,
                f"[{enabled_style}]{enabled_str}[/{enabled_style}]",
                task_def.cron,
                schedule,
            )

        console.print(table)

    return Command(
        name="status",
        callback=status_callback,
        help="Show all registered scheduled tasks and their status",
    )


def _build_command_for_task(task_def: ScheduledTaskDef) -> click.Command:
    """Build a Click command from a ScheduledTaskDef.

    The generated command:
    1. Initializes the app
    2. Opens the lifespan context
    3. Calls the scheduled task function with the provided options
    """
    from fastedgy.cli import Command, initialize_app, pass_cli_context, CliContext

    func = task_def.func

    async def command_callback(ctx: CliContext, **kwargs: Any):
        async with ctx.lifespan():
            if asyncio.iscoroutinefunction(func):
                await func(**kwargs)
            else:
                func(**kwargs)

    wrapped = initialize_app(pass_cli_context(command_callback))

    cmd = Command(
        name=task_def.name,
        callback=wrapped,
        help=task_def.description or task_def.func.__doc__ or "",
    )

    for opt in task_def.options:
        cmd.params.append(opt)

    return cmd


def register_scheduler_cli_commands(cli: click.Group) -> None:
    """Discover scheduled tasks and register the scheduler CLI group.

    This is the main entry point called from fastedgy.cli.main().
    Silently does nothing if no scheduler package exists or no tasks are registered.

    Args:
        cli: The root CLI group to register the scheduler group into.
    """
    from fastedgy.queued_task.scheduler.discovery import discover_scheduled_tasks

    discover_scheduled_tasks("scheduler")

    registry = get_service(ScheduledTaskRegistry)

    if len(registry) > 0:
        scheduler_group = create_scheduler_cli_group()
        cli.add_command(scheduler_group)
        logger.debug(f"Registered scheduler CLI group with {len(registry)} command(s)")
