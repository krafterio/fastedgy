# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.test import tasks

from .helpers import queue


async def test_get_task_by_id_returns_the_task(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert task.id is not None

    fetched = await queue().get_task_by_id(task.id)

    assert fetched is not None
    assert fetched.id == task.id


async def test_get_task_by_id_unknown_returns_none(setup_db: FastEdgy) -> None:
    assert await queue().get_task_by_id(999999) is None


async def test_get_pending_tasks_count_counts_only_enqueued(setup_db: FastEdgy) -> None:
    await queue().add_task_async(tasks.add_numbers, 1, 2)
    await queue().add_task_async(tasks.add_numbers, 3, 4)

    done = await queue().add_task_async(tasks.add_numbers, 5, 6)
    assert done.id is not None
    done = await queue().get_task_by_id(done.id)
    assert done is not None
    done.mark_as_done()
    await done.save()

    assert await queue().get_pending_tasks_count() == 2


async def test_get_task_status_returns_a_status_dict(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert task.id is not None

    status = await queue().get_task_status(task.id)

    assert status is not None
    assert status["id"] == task.id
    assert status["name"] == "fastedgy.test.tasks.add_numbers"
    assert status["state"] == QueuedTaskState.enqueued
    assert status["is_active"] is True
    assert status["is_finished"] is False
    assert status["parent_task"] is None


async def test_get_task_status_unknown_returns_none(setup_db: FastEdgy) -> None:
    assert await queue().get_task_status(999999) is None
