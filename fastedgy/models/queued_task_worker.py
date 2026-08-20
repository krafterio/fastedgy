# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.base import BaseModel
from fastedgy.queued_task.models.queued_task_worker import QueuedTaskWorkerMixin


class BaseQueuedTaskWorker(QueuedTaskWorkerMixin, BaseModel):
    class Meta(QueuedTaskWorkerMixin.Meta, BaseModel.Meta):
        abstract = True
