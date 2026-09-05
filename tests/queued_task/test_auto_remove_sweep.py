# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

import pytest

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.queued_task.models.queued_task import QueuedTaskState
from fastedgy.queued_task.models.queued_task_log import QueuedTaskLogType
from fastedgy.queued_task.services.queue_worker_manager import QueueWorkerManager
from fastedgy.test.models.queued_task_log import QueuedTaskLog

from .helpers import queue


async def _log_error(task: Any) -> None:
    await QueuedTaskLog(task=task, log_type=QueuedTaskLogType.error, message="boom").save()


def manager(monkeypatch: pytest.MonkeyPatch, delay: int = 0) -> QueueWorkerManager:
    m = get_service(QueueWorkerManager)
    monkeypatch.setattr(m.config, "auto_remove_delay", delay)

    return m


async def _done(auto_remove: bool = True, **kwargs: Any) -> Any:
    created = await queue().create_task(
        module_name="fastedgy.test.tasks",
        function_name="add_numbers",
        auto_remove=auto_remove,
        **kwargs,
    )

    # create_task hands back an instance whose state was restored from the
    # pre-insert snapshot, so saving it again writes nothing: reload it.
    task = await queue().get_task_by_id(created.id)
    assert task is not None
    task.mark_as_done()
    await task.save()

    return task


async def test_sweep_removes_a_completed_task(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    task = await _done()

    await manager(monkeypatch)._sweep_auto_removable_tasks()

    assert await queue().get_task_by_id(task.id) is None


async def test_sweep_keeps_a_task_inside_its_grace_period(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    task = await _done()

    await manager(monkeypatch, delay=3600)._sweep_auto_removable_tasks()

    assert await queue().get_task_by_id(task.id) is not None


async def test_sweep_keeps_a_task_without_auto_remove(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    task = await _done(auto_remove=False)

    await manager(monkeypatch)._sweep_auto_removable_tasks()

    assert await queue().get_task_by_id(task.id) is not None


async def test_sweep_keeps_a_task_carrying_an_error_log(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    kept = await _done()
    await _log_error(kept)
    removed = await _done()

    await manager(monkeypatch)._sweep_auto_removable_tasks()

    assert await queue().get_task_by_id(kept.id) is not None
    assert await queue().get_task_by_id(removed.id) is None


async def test_sweep_keeps_a_task_that_is_not_done(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    task = await queue().create_task(
        module_name="fastedgy.test.tasks",
        function_name="add_numbers",
        auto_remove=True,
    )

    await manager(monkeypatch)._sweep_auto_removable_tasks()

    reloaded = await queue().get_task_by_id(task.id)
    assert reloaded is not None
    assert reloaded.state == QueuedTaskState.enqueued


async def test_sweep_unwinds_a_whole_chain_leaf_first(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    root = await _done()
    middle = await _done(parent_task=root)
    leaf = await _done(parent_task=middle)

    assert middle.parent_task is not None
    assert leaf.parent_task is not None

    await manager(monkeypatch)._sweep_auto_removable_tasks()

    assert await queue().get_task_by_id(leaf.id) is None
    assert await queue().get_task_by_id(middle.id) is None
    assert await queue().get_task_by_id(root.id) is None


async def test_sweep_keeps_the_ancestors_of_a_flagged_leaf(setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch) -> None:
    root = await _done()
    leaf = await _done(parent_task=root)
    await _log_error(leaf)

    await manager(monkeypatch)._sweep_auto_removable_tasks()

    assert await queue().get_task_by_id(leaf.id) is not None
    assert await queue().get_task_by_id(root.id) is not None
