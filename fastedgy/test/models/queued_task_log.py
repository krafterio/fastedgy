# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.queued_task_log import BaseQueuedTaskLog


class QueuedTaskLog(BaseQueuedTaskLog):
    class Meta(BaseQueuedTaskLog.Meta):
        tablename = "queued_task_logs"


__all__ = [
    "QueuedTaskLog",
]
