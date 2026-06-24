# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.queued_task.services.queue_hooks import QueueHookRegistry

from .helpers import queue


async def test_post_create_hook_fires_after_save(setup_db: FastEdgy) -> None:
    registry = get_service(QueueHookRegistry)
    seen: list[Any] = []

    async def hook(task: Any) -> None:
        seen.append(task.id)

    registry.register_post_create(hook)

    try:
        task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
        assert task.id in seen
    finally:
        registry.on_post_create_hooks.remove(hook)


async def test_pre_create_hook_fires_before_save(setup_db: FastEdgy) -> None:
    registry = get_service(QueueHookRegistry)
    seen: list[Any] = []

    async def hook(task: Any) -> None:
        seen.append(getattr(task, "id", None))

    registry.register_pre_create(hook)

    try:
        await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
        assert seen == [None]
    finally:
        registry.on_pre_create_hooks.remove(hook)
