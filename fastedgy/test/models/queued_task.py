# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.queued_task import BaseQueuedTask


class QueuedTask(BaseQueuedTask):
    class Meta(BaseQueuedTask.Meta):
        tablename = "queued_tasks"


__all__ = [
    "QueuedTask",
]
