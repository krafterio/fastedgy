# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task import QueuedTaskState

from .helpers import queue


async def test_create_task_with_module_and_function(setup_db: FastEdgy) -> None:
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers", args=[1, 2])

    assert task.id
    assert task.state == QueuedTaskState.enqueued
    assert task.name == "fastedgy.test.tasks.add_numbers"
    assert task.date_enqueued is not None


async def test_create_task_requires_a_callable_reference(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        await queue().create_task(args=[1])


async def test_create_task_preserves_context_and_adds_workspace_keys(setup_db: FastEdgy) -> None:
    task = await queue().create_task(
        module_name="fastedgy.test.tasks",
        function_name="add_numbers",
        context={"foo": "bar"},
    )

    assert task.context["foo"] == "bar"
    assert task.context["_workspace_id"] is None
    assert task.context["_user_id"] is None


async def test_create_task_sets_auto_remove(setup_db: FastEdgy) -> None:
    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers", auto_remove=True)

    assert task.auto_remove is True


async def test_create_task_keeps_an_explicit_name(setup_db: FastEdgy) -> None:
    task = await queue().create_task(module_name="module", function_name="func", name="custom-name")

    assert task.name == "custom-name"


async def test_create_task_with_vanished_parent_enqueues_unchained(setup_db: FastEdgy) -> None:
    parent = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")
    await parent.delete()

    task = await queue().create_task(
        module_name="fastedgy.test.tasks",
        function_name="add_numbers",
        parent_task=parent,
    )

    assert task.id
    assert task.parent_task is None
    assert task.state == QueuedTaskState.enqueued
