# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.queued_task.scheduler.cli import register_scheduler_cli_commands
from fastedgy.queued_task.scheduler.cron_scheduler import CronScheduler
from fastedgy.queued_task.scheduler.decorators import Option, option, scheduled_task
from fastedgy.queued_task.scheduler.discovery import discover_scheduled_tasks
from fastedgy.queued_task.scheduler.registry import (
    ScheduledTaskDef,
    ScheduledTaskRegistry,
)
from fastedgy.queued_task.scheduler.service import Scheduler

__all__ = [
    "CronScheduler",
    "Option",
    "ScheduledTaskDef",
    "ScheduledTaskRegistry",
    "Scheduler",
    "discover_scheduled_tasks",
    "option",
    "register_scheduler_cli_commands",
    "scheduled_task",
]
