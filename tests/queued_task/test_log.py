# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.queued_task.models.queued_task_log import QueuedTaskLogType
from fastedgy.test import tasks
from fastedgy.test.models.queued_task_log import QueuedTaskLog

from .helpers import queue


async def test_create_log_sets_logged_at(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)

    log = QueuedTaskLog(task=task, log_type=QueuedTaskLogType.info, name="start", message="task started")
    await log.save()

    assert log.id
    assert log.logged_at is not None
    assert log.log_type == QueuedTaskLogType.info
    assert log.message == "task started"


async def test_logs_are_linked_to_their_task(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)

    await QueuedTaskLog(task=task, log_type=QueuedTaskLogType.error, message="boom").save()
    await QueuedTaskLog(task=task, log_type=QueuedTaskLogType.info, message="ok").save()

    count = await QueuedTaskLog.query.filter(QueuedTaskLog.columns.task == task.id).count()

    assert count == 2


async def test_logs_are_removed_when_the_task_is_deleted(setup_db: FastEdgy) -> None:
    task = await queue().add_task_async(tasks.add_numbers, 1, 2)
    await QueuedTaskLog(task=task, log_type=QueuedTaskLogType.info, message="ok").save()

    await task.delete()

    count = await QueuedTaskLog.query.filter(QueuedTaskLog.columns.task == task.id).count()

    assert count == 0
