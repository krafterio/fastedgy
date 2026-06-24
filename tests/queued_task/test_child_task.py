# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.test import tasks

from .helpers import queue


async def test_create_child_task_links_parent(setup_db: FastEdgy) -> None:
    parent = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert parent.id is not None

    child = await queue().create_child_task(
        parent.id,
        module_name="fastedgy.test.tasks",
        function_name="add_numbers",
    )

    assert child.parent_task is not None
    assert child.parent_task.id == parent.id


async def test_add_child_task_async_links_parent(setup_db: FastEdgy) -> None:
    parent = await queue().add_task_async(tasks.add_numbers, 1, 2)
    assert parent.id is not None

    child = await queue().add_child_task_async(parent.id, tasks.add_numbers, 3, 4)

    assert child.parent_task is not None
    assert child.parent_task.id == parent.id
    assert child.args == [3, 4]


async def test_create_child_task_with_unknown_parent_is_rejected(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        await queue().create_child_task(999999, module_name="module", function_name="func")


async def test_add_child_task_async_with_unknown_parent_is_rejected(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        await queue().add_child_task_async(999999, tasks.add_numbers, 1, 2)
