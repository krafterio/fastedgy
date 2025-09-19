# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

from typing import List, Callable, Any, Optional, TYPE_CHECKING, Awaitable

from fastedgy.dependencies import get_service

if TYPE_CHECKING:
    from fastedgy.models.queued_task import BaseQueuedTask as QueuedTask


logger = logging.getLogger("queued_task.hooks")


class QueueHookRegistry:
    """Registry for managing task lifecycle hooks"""

    def __init__(self):
        self.on_pre_create_hooks: List[Callable] = []
        self.on_post_create_hooks: List[Callable] = []
        self.on_pre_run_hooks: List[Callable] = []
        self.on_post_run_hooks: List[Callable] = []

    def register_pre_create(self, func: Callable) -> None:
        """Register a pre-create hook"""
        self.on_pre_create_hooks.append(func)
        logger.debug(f"Registered on_pre_create hook: {func.__name__}")

    def register_post_create(self, func: Callable) -> None:
        """Register a post-create hook"""
        self.on_post_create_hooks.append(func)
        logger.debug(f"Registered on_post_create hook: {func.__name__}")

    def register_pre_run(self, func: Callable) -> None:
        """Register a pre-run hook"""
        self.on_pre_run_hooks.append(func)
        logger.debug(f"Registered on_pre_run hook: {func.__name__}")

    def register_post_run(self, func: Callable) -> None:
        """Register a post-run hook"""
        self.on_post_run_hooks.append(func)
        logger.debug(f"Registered on_post_run hook: {func.__name__}")

    async def trigger_pre_create(self, task: "QueuedTask") -> None:
        """Trigger all pre create hooks"""
        for hook in self.on_pre_create_hooks:
            try:
                await hook(task)
            except Exception as e:
                logger.error(f"Error in on_pre_create hook {hook.__name__}: {e}")

    async def trigger_post_create(self, task: "QueuedTask") -> None:
        """Trigger all post create hooks"""
        for hook in self.on_post_create_hooks:
            try:
                await hook(task)
            except Exception as e:
                logger.error(f"Error in on_post_create hook {hook.__name__}: {e}")

    async def trigger_pre_run(self, task: "QueuedTask") -> None:
        """Trigger all pre run hooks"""
        for hook in self.on_pre_run_hooks:
            try:
                await hook(task)
            except Exception as e:
                logger.error(f"Error in on_pre_run hook {hook.__name__}: {e}")

    async def trigger_post_run(
        self, task: "QueuedTask", result: Any = None, error: Exception | None = None
    ) -> None:
        """Trigger all post run hooks"""
        for hook in self.on_post_run_hooks:
            try:
                await hook(task, result=result, error=error)
            except Exception as e:
                logger.error(f"Error in on_post_run hook {hook.__name__}: {e}")

    def clear_all_hooks(self) -> None:
        """Clear all registered hooks (useful for testing)"""
        self.on_pre_create_hooks.clear()
        self.on_post_create_hooks.clear()
        self.on_pre_run_hooks.clear()
        self.on_post_run_hooks.clear()
        logger.debug("Cleared all registered hooks")


# Decorator functions that use the global registry
def on_pre_create(func: Callable[["QueuedTask"], Awaitable[None]]) -> Callable:
    """Decorator to register a function to run before task creation (between new and save)"""
    registry = get_service(QueueHookRegistry)
    registry.register_pre_create(func)
    return func


def on_post_create(func: Callable[["QueuedTask"], Awaitable[None]]) -> Callable:
    """Decorator to register a function to run after task creation"""
    registry = get_service(QueueHookRegistry)
    registry.register_post_create(func)
    return func


def on_pre_run(func: Callable[["QueuedTask"], Awaitable[None]]) -> Callable:
    """Decorator to register a function to run before task execution"""
    registry = get_service(QueueHookRegistry)
    registry.register_pre_run(func)
    return func


def on_post_run(
    func: Callable[["QueuedTask", Any, Optional[Exception]], Awaitable[None]],
) -> Callable:
    """Decorator to register a function to run after task execution"""
    registry = get_service(QueueHookRegistry)
    registry.register_post_run(func)
    return func
