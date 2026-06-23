# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.queued_task_log import BaseQueuedTaskLog
from fastedgy.api_route_model import api_route_model


@api_route_model()
class QueuedTaskLog(BaseQueuedTaskLog):
    class Meta(BaseQueuedTaskLog.Meta):
        tablename = "queued_task_logs"


__all__ = [
    "QueuedTaskLog",
]
