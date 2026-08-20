# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.queued_task_worker import BaseQueuedTaskWorker


@api_route_model()
class QueuedTaskWorker(BaseQueuedTaskWorker):
    class Meta(BaseQueuedTaskWorker.Meta):
        tablename = "queued_task_workers"


__all__ = [
    "QueuedTaskWorker",
]
