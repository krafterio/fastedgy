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


async def test_create_task_replays_serialization_conflict_from_pristine_state(
    setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import Any

    from sqlalchemy.exc import DBAPIError

    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry

    class _SerializationOrig(Exception):
        sqlstate = "40001"

    QueuedTask = get_service(Registry).get_model("QueuedTask")
    real_save = QueuedTask.save
    attempts = {"n": 0}

    # The rolled-back INSERT leaves pk + defaults on the instance: without the
    # pristine restore, the replay lazy-loads / UPDATEs the vanished row.
    async def flaky_save(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = await real_save(self, *args, **kwargs)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise DBAPIError("INSERT", None, _SerializationOrig())
        return result

    monkeypatch.setattr(QueuedTask, "save", flaky_save)

    task = await queue().create_task(module_name="fastedgy.test.tasks", function_name="add_numbers")

    assert attempts["n"] == 2
    assert task.id
    assert task.state == QueuedTaskState.enqueued
    assert await QueuedTask.query.filter(QueuedTask.columns.id == task.id).count() == 1


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
