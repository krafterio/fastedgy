# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import cli
from fastedgy.queued_task.cli import queue as cli_queue


@cli.group()
def queue():
    """Queue management commands."""
    pass


@queue.command()
@cli.pass_cli_context
async def status(ctx: cli.CliContext):
    """Show queue system status."""
    await cli_queue.status(ctx)


@queue.command()
@cli.pass_cli_context
async def clear(ctx: cli.CliContext):
    """Clear all pending tasks from the queue."""
    await cli_queue.clear(ctx)


@queue.command()
@cli.argument("task_id", type=int)
@cli.pass_cli_context
async def retry(ctx: cli.CliContext, task_id: int):
    """Retry a task by ID (clone if done, re-enqueue if stopped)."""
    await cli_queue.retry(ctx, task_id)


@queue.command()
@cli.pass_cli_context
async def servers(ctx: cli.CliContext):
    """Show detailed information about all queue servers."""
    await cli_queue.servers(ctx)


@queue.command()
@cli.option(
    "--workers", default=-1, help="Number of workers to start (-1 = auto detect)"
)
@cli.option(
    "--no-scheduler", is_flag=True, default=False, help="Disable the cron scheduler"
)
@cli.pass_cli_context
async def start(ctx: cli.CliContext, workers: int, no_scheduler: bool):
    """Start queue workers only (no HTTP server)."""
    await cli_queue.start(ctx, workers, no_scheduler)


@queue.command()
@cli.pass_cli_context
async def stats(ctx: cli.CliContext):
    """Show detailed queue system statistics."""
    await cli_queue.stats(ctx)
