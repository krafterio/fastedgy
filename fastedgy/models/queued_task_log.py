# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model.params import OrderByList
from fastedgy.queued_task.models.queued_task_log import QueuedTaskLogMixin


class BaseQueuedTaskLog(QueuedTaskLogMixin):
    class Meta: # type: ignore
        abstract = True
        default_order_by: OrderByList = [("logged_at", "desc")]
