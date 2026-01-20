# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm.order_by import OrderByList
from fastedgy.queued_task.models.queued_task import QueuedTaskMixin


class BaseQueuedTask(QueuedTaskMixin):
    class Meta(QueuedTaskMixin.Meta):
        abstract = True
        default_order_by: OrderByList = [("date_enqueued", "desc"), ("state", "asc")]
