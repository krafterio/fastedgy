# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from os import cpu_count
from typing import cast

from fastedgy.cli import console, Table, CliContext

from fastedgy.orm import Registry
from fastedgy.queued_task.services.queued_tasks import QueuedTasks
from fastedgy.queued_task.services.queue_worker_manager import QueueWorkerManager


async def status(ctx: CliContext):
    """Show queue system status"""
    console.print("[yellow]Checking queue system status...[/yellow]")

    async with ctx.lifespan():
        try:
            service = ctx.get(QueuedTasks)

            pending_count = await service.get_pending_tasks_count()
            global_stats = await QueueWorkerManager.get_global_stats()

            table = Table(title="Queue System Status (Global)")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="yellow")

            table.add_row("Pending Tasks", str(pending_count))
            table.add_row("Active Servers", str(global_stats["servers"]))
            table.add_row("Total Workers", f"{global_stats['total_workers']}/{global_stats['max_workers']}")
            table.add_row("Active Workers", str(global_stats["active_workers"]))
            table.add_row("Idle Workers", str(global_stats["idle_workers"]))

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error checking status: {str(e)}[/red]")


async def clear(ctx: CliContext):
    """Clear all pending tasks from the queue"""
    console.print("[yellow]Clearing all pending tasks...[/yellow]")

    async with ctx.lifespan():
        try:
            from fastedgy.models.queued_task import BaseQueuedTask
            from fastedgy.queued_task.models.queued_task import QueuedTaskState
            QueuedTask = cast(type["BaseQueuedTask"], ctx.get(Registry).get_model("QueuedTask"))

            # Delete all enqueued tasks
            deleted_count = await QueuedTask.query.filter(
                QueuedTask.columns.state == QueuedTaskState.enqueued
            ).delete()

            console.print(f"[green]Cleared {deleted_count} pending tasks[/green]")

        except Exception as e:
            console.print(f"[red]Error clearing tasks: {str(e)}[/red]")


async def start(ctx: CliContext, workers: int | None):
    """Start queue workers only (no HTTP server)"""
    console.print(f"[yellow]Starting {workers} queue workers...[/yellow]")
    console.print("[green]Starting workers in queue-only mode[/green]")
    console.print("[yellow]Press Ctrl+C to stop workers[/yellow]")

    async with ctx.lifespan():
        try:
            worker_service = ctx.get(QueueWorkerManager)

            workers = cpu_count() or 1 if workers is None or workers < 0 else workers

            # Override max workers if specified
            if workers != worker_service.max_workers:
                worker_service.max_workers = workers
                worker_service.worker_pool.max_workers = workers

            await worker_service.start_workers(workers)

        except Exception as e:
            console.print(f"[red]Error starting workers: {str(e)}[/red]")


async def stats(ctx: CliContext):
    """Show detailed queue system statistics"""
    console.print("[yellow]Fetching detailed queue statistics...[/yellow]")

    async with ctx.lifespan():
        try:
            from fastedgy.models.queued_task import BaseQueuedTask
            from fastedgy.queued_task.models.queued_task import QueuedTaskState
            QueuedTask = cast(type["BaseQueuedTask"], ctx.get(Registry).get_model("QueuedTask"))

            # Get task counts by state
            total_tasks = await QueuedTask.query.count()
            enqueued_tasks = await QueuedTask.query.filter(QueuedTask.columns.state == QueuedTaskState.enqueued).count()
            doing_tasks = await QueuedTask.query.filter(QueuedTask.columns.state == QueuedTaskState.doing).count()
            done_tasks = await QueuedTask.query.filter(QueuedTask.columns.state == QueuedTaskState.done).count()
            failed_tasks = await QueuedTask.query.filter(QueuedTask.columns.state == QueuedTaskState.failed).count()
            cancelled_tasks = await QueuedTask.query.filter(
                QueuedTask.columns.state == QueuedTaskState.cancelled).count()

            # Get global worker stats
            global_stats = await QueueWorkerManager.get_global_stats()

            # Create statistics table
            table = Table(title="Detailed Queue Statistics")
            table.add_column("Category", style="cyan")
            table.add_column("Count", style="yellow")

            # Task statistics
            table.add_row("=== TASKS ===", "")
            table.add_row("Total Tasks", str(total_tasks))
            table.add_row("Enqueued", str(enqueued_tasks))
            table.add_row("Doing", str(doing_tasks))
            table.add_row("Done", str(done_tasks))
            table.add_row("Failed", str(failed_tasks))
            table.add_row("Cancelled", str(cancelled_tasks))

            # Worker statistics
            table.add_row("", "")
            table.add_row("=== WORKERS ===", "")
            table.add_row("Active Servers", str(global_stats["servers"]))
            table.add_row("Total Workers", f"{global_stats['total_workers']}/{global_stats['max_workers']}")
            table.add_row("Active Workers", str(global_stats["active_workers"]))
            table.add_row("Idle Workers", str(global_stats["idle_workers"]))

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error fetching statistics: {str(e)}[/red]")


async def retry(ctx: CliContext, task_ids):
    """Retry failed or stopped tasks by ID"""
    console.print(f"[yellow]Retrying tasks: {', '.join(map(str, task_ids))}[/yellow]")

    async with ctx.lifespan():
        try:
            service = ctx.get(QueuedTasks)
            retried_count = 0

            for task_id in task_ids:
                try:
                    retried_task = await service.retry_task(task_id)
                    console.print(f"[green]Task {task_id} retried with new ID: {retried_task.id}[/green]")
                    retried_count += 1
                except Exception as e:
                    console.print(f"[red]Failed to retry task {task_id}: {str(e)}[/red]")

            console.print(f"[cyan]Successfully retried {retried_count}/{len(task_ids)} tasks[/cyan]")

        except Exception as e:
            console.print(f"[red]Error retrying tasks: {str(e)}[/red]")


async def servers(ctx: CliContext):
    """List all active queue servers"""
    console.print("[yellow]Fetching active queue servers...[/yellow]")

    async with ctx.lifespan():
        try:
            from fastedgy.models.queued_task_worker import BaseQueuedTaskWorker
            QueuedTaskWorker = cast(type["BaseQueuedTaskWorker"], ctx.get(Registry).get_model("QueuedTaskWorker"))

            servers = await QueuedTaskWorker.query.all()

            if not servers:
                console.print("[yellow]No queue servers found[/yellow]")
                return

            table = Table(title="Queue Servers")
            table.add_column("Server", style="cyan")
            table.add_column("Status", style="yellow")
            table.add_column("Workers", style="green")
            table.add_column("Active", style="blue")
            table.add_column("Idle", style="magenta")
            table.add_column("Last Heartbeat", style="white")

            for server in servers:
                status = "🟢 Running" if server.is_running and server.is_alive else "🔴 Stopped"
                workers = f"{server.total_workers}/{server.max_workers}"

                table.add_row(
                    server.server_name,
                    status,
                    workers,
                    str(server.active_workers),
                    str(server.idle_workers),
                    server.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if server.last_heartbeat else "Never"
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error fetching servers: {str(e)}[/red]")
