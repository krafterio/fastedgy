# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.test import tasks
from fastedgy.test.models.category import Category

from .helpers import queue, run_task_now


async def test_run_task_success_marks_done(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 2, 3, max_retries=0)

    result, reloaded = await run_task_now(task)

    assert result["status"] == "success"
    assert result["result"] == 5
    assert reloaded.state == QueuedTaskState.done
    assert reloaded.date_done is not None
    assert reloaded.execution_time >= 0


async def test_run_task_failure_marks_failed(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.boom, "kaboom", max_retries=0)

    result, reloaded = await run_task_now(task)

    assert result["status"] == "error"
    assert reloaded.state == QueuedTaskState.failed
    assert reloaded.exception_name == "ValueError"
    assert reloaded.exception_message == "kaboom"


async def test_run_task_failure_within_budget_reenqueues(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.boom, max_retries=2)

    result, reloaded = await run_task_now(task)

    assert result["status"] == "retry"
    assert reloaded.state == QueuedTaskState.enqueued
    assert reloaded.retry_count == 1


async def test_run_async_task_performs_db_side_effect(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.make_category, "FromTask", max_retries=0)

    result, reloaded = await run_task_now(task)

    assert result["status"] == "success"
    assert reloaded.state == QueuedTaskState.done
    assert await Category.query.filter(Category.columns.name == "FromTask").count() == 1
