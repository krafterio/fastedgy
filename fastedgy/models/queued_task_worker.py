# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.queued_task.models.queued_task_worker import QueuedTaskWorkerMixin
from fastedgy.models.base import BaseModel


class BaseQueuedTaskWorker(QueuedTaskWorkerMixin, BaseModel):
    class Meta:  # type: ignore
        abstract = True
