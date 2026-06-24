# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.dependencies import get_service
from fastedgy.queued_task.services.queue_worker import QueueWorker
from fastedgy.queued_task.services.queued_tasks import QueuedTasks


def queue() -> QueuedTasks:
    return get_service(QueuedTasks)


async def run_task_now(task: Any, worker_id: str = "test-worker") -> tuple[dict[str, Any], Any]:
    claimed = await queue().get_task_by_id(task.id)
    assert claimed is not None
    claimed.mark_as_doing()
    await claimed.save()

    result = await QueueWorker(worker_id).run_task(claimed)
    reloaded = await queue().get_task_by_id(task.id)

    return result, reloaded
