# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.test import tasks

from .helpers import queue


async def test_add_task_async_creates_enqueued_task(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 2, 3)

    assert task.id
    assert task.state == QueuedTaskState.enqueued
    assert task.module_name == "fastedgy.test.tasks"
    assert task.function_name == "add_numbers"
    assert task.name == "fastedgy.test.tasks.add_numbers"
    assert task.args == [2, 3]
    assert task.date_enqueued is not None
    assert task.channel == "default"
    assert task.priority == 0


async def test_add_task_async_stores_kwargs(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, a=1, b=2)

    assert task.kwargs == {"a": 1, "b": 2}


async def test_add_task_async_honours_channel_priority_and_retries(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2, channel="sync", priority=5, max_retries=7)

    assert task.channel == "sync"
    assert task.priority == 5
    assert task.max_retries == 7


async def test_add_task_async_serializes_local_function(setup_db: FastEdgy) -> None:
    def local_add(a: int, b: int) -> int:
        return a + b

    task = await queue().add_task_async(local_add, 1, 2)

    assert task.serialized_function is not None
    assert task.module_name is None
    assert task.function_name is None


async def test_add_task_async_rejects_instance_methods(setup_db: FastEdgy) -> None:
    class Holder:
        def run(self) -> None: ...

    with pytest.raises(ValueError):
        await queue().add_task_async(Holder().run)


async def test_add_task_async_rejects_non_serializable_args(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        await queue().add_task_async(tasks.add_numbers, object())
