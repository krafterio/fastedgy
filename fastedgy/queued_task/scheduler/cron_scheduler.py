# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from cronsim import CronSim

from fastedgy import context as fastedgy_context
from fastedgy.dependencies import get_service
from fastedgy.orm import Database
from fastedgy.queued_task.services.queued_tasks import QueuedTasks
from fastedgy.queued_task.scheduler.registry import (
    ScheduledTaskRegistry,
    ScheduledTaskDef,
)

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask

logger = logging.getLogger("queued_task.scheduler")


class CronScheduler:
    """Evaluates cron expressions and creates QueuedTasks at the right time.

    Integrated into QueueWorkerManager as an additional async task.
    Runs in a loop, sleeping until the next minute boundary, then checking
    all registered scheduled tasks.
    """

    def __init__(self):
        self._running = False

    async def run(self) -> None:
        """Main scheduler loop.

        Wakes up at the start of every minute and checks which cron
        expressions match the current time. For each match, creates a
        QueuedTask (with duplicate prevention).
        """
        self._running = True
        registry = get_service(ScheduledTaskRegistry)

        enabled_tasks = {
            name: td
            for name, td in registry.get_all().items()
            if registry.is_task_enabled(name)
        }

        logger.info(f"CronScheduler started with {len(enabled_tasks)} active task(s)")

        for name, task_def in enabled_tasks.items():
            logger.info(f"  - {name}: cron='{task_def.cron}'")

        while self._running:
            try:
                # Sleep until the start of the next minute
                now = datetime.now(fastedgy_context.get_timezone())
                seconds_to_next_minute = 60 - now.second - now.microsecond / 1_000_000
                await asyncio.sleep(seconds_to_next_minute)

                if not self._running:
                    break

                # Evaluate all cron expressions at the current minute
                now = datetime.now(fastedgy_context.get_timezone())
                current_minute = now.replace(second=0, microsecond=0)

                for name, task_def in registry.get_all().items():
                    try:
                        if not registry.is_task_enabled(name):
                            continue

                        if self._cron_matches(task_def.cron, current_minute):
                            logger.debug(f"Cron match for '{name}' at {current_minute}")
                            await self._create_task_if_not_exists(task_def)
                    except Exception as e:
                        logger.error(f"Error evaluating cron for '{name}': {e}")

            except asyncio.CancelledError:
                logger.debug("CronScheduler cancelled")
                break
            except Exception as e:
                logger.error(f"CronScheduler loop error: {e}")
                await asyncio.sleep(5)

        logger.info("CronScheduler stopped")

    def stop(self) -> None:
        self._running = False

    def _cron_matches(self, cron_expr: str, dt: datetime) -> bool:
        """Check if a cron expression matches the given datetime.

        Uses cronsim to compute the next occurrence from one minute before
        the target time. If the next occurrence equals the target, it matches.
        """
        one_minute_before = dt - timedelta(minutes=1)
        it = CronSim(cron_expr, one_minute_before)
        next_fire = next(it)
        return next_fire == dt

    async def _create_task_if_not_exists(self, task_def: ScheduledTaskDef) -> None:
        """Create a QueuedTask for the scheduled task, with duplicate prevention."""
        try:
            from sqlalchemy import text

            database: Database = get_service(Database)
            check_sql = text(
                "SELECT 1 FROM queued_tasks "
                "WHERE name = :name AND state IN ('enqueued', 'waiting', 'doing') "
                "LIMIT 1"
            ).bindparams(name=task_def.name)
            existing = await database.fetch_one(check_sql)

            if existing:
                logger.debug(f"Skipping '{task_def.name}': already has an active task")
                return

            queued_tasks = get_service(QueuedTasks)
            task = await queued_tasks.create_task(
                module_name=task_def.module_name,
                function_name=task_def.function_name,
                args=[],
                kwargs={},
                context=task_def.context or {},
                name=task_def.name,
                auto_remove=task_def.auto_remove,
            )

            logger.info(f"Created cron task '{task_def.name}' (id={task.id})")

        except Exception as e:
            logger.error(f"Error creating cron task '{task_def.name}': {e}")
