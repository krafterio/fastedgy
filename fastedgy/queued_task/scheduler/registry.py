# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from fastedgy.dependencies import Inject
import rich_click as click

from fastedgy.config import BaseSettings, get_service


logger = logging.getLogger("queued_task.scheduler")


@dataclass
class ScheduledTaskDef:
    """Definition of a scheduled task registered via @scheduled_task."""

    name: str
    cron: str
    func: Callable
    description: str = ""
    options: list[click.Option] = field(default_factory=list)
    auto_remove: bool = True
    enabled: bool = True
    context: Optional[Dict[str, Any]] = None

    @property
    def module_name(self) -> str:
        return self.func.__module__

    @property
    def function_name(self) -> str:
        return self.func.__name__


class ScheduledTaskRegistry:
    """Global registry for scheduled task definitions.

    Works like QueueHookRegistry / Bus -- a singleton accessed via get_service().
    Decorators register tasks at import time.
    """

    def __init__(self, settings: BaseSettings | None = None):
        self.__settings = settings
        self._tasks: Dict[str, ScheduledTaskDef] = {}

    @property
    def _settings(self) -> BaseSettings:
        if not self.__settings:
            self.__settings = get_service(BaseSettings)

        return self.__settings

    def register(self, task_def: ScheduledTaskDef) -> None:
        if task_def.name in self._tasks:
            logger.warning(
                f"Scheduled task '{task_def.name}' is already registered, overwriting"
            )
        self._tasks[task_def.name] = task_def
        logger.debug(
            f"Registered scheduled task '{task_def.name}' "
            f"(cron='{task_def.cron}', func={task_def.module_name}.{task_def.function_name})"
        )

    def get(self, name: str) -> Optional[ScheduledTaskDef]:
        return self._tasks.get(name)

    def get_all(self) -> Dict[str, ScheduledTaskDef]:
        return dict(self._tasks)

    def is_task_enabled(self, name: str) -> bool:
        """Resolve whether a task is enabled.

        Priority (highest to lowest):
        1. Explicit name in disabled_scheduled_tasks -> disabled
        2. Explicit name in enabled_scheduled_tasks -> enabled
        3. 'all' or '*' in disabled_scheduled_tasks -> disabled
        4. Decorator ``enabled`` value
        """
        task_def = self._tasks.get(name)

        if task_def is None:
            return False

        disabled = self._settings.disabled_scheduled_tasks
        enabled = self._settings.enabled_scheduled_tasks

        if task_def.name in disabled:
            return False

        if task_def.name in enabled:
            return True

        if "all" in disabled or "*" in disabled:
            return False

        return task_def.enabled

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, name: str) -> bool:
        return name in self._tasks
