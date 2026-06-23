# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.queued_task import BaseQueuedTask
from fastedgy.api_route_model import api_route_model


@api_route_model()
class QueuedTask(BaseQueuedTask):
    class Meta(BaseQueuedTask.Meta):
        tablename = "queued_tasks"


__all__ = [
    "QueuedTask",
]
