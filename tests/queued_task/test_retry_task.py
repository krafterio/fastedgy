# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.test import tasks

from .helpers import queue


async def test_retry_failed_task_clones_it(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert task.id is not None
    loaded = await queue().get_task_by_id(task.id)
    assert loaded is not None
    loaded.mark_as_failed(exception_name="ValueError", exception_message="boom")
    await loaded.save()

    clone = await queue().retry_task(task.id)

    assert clone.id != task.id
    assert clone.name == f"{task.name}_retry"
    assert clone.state == QueuedTaskState.enqueued
    assert clone.module_name == task.module_name
    assert clone.retry_count == 0


async def test_retry_stopped_task_reenqueues_the_same_task(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert task.id is not None
    loaded = await queue().get_task_by_id(task.id)
    assert loaded is not None
    loaded.mark_as_stopped()
    await loaded.save()

    retried = await queue().retry_task(task.id)

    assert retried.id == task.id
    assert retried.state == QueuedTaskState.enqueued
    assert retried.date_stopped is None


async def test_retry_enqueued_task_is_rejected(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert task.id is not None

    with pytest.raises(ValueError):
        await queue().retry_task(task.id)


async def test_retry_running_task_is_rejected(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert task.id is not None
    task.mark_as_doing()
    await task.save()

    with pytest.raises(ValueError):
        await queue().retry_task(task.id)


async def test_retry_unknown_task_is_rejected(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        await queue().retry_task(999999)
