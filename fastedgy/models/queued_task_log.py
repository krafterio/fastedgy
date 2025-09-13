# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.api_route_model.params import OrderByList
from fastedgy.queued_task.models.queued_task_log import QueuedTaskLogMixin


@api_route_model(
    list=True,
    get=True,
    create=False,
    patch=False,
    delete=False,
    export=False,
)
class BaseQueuedTaskLog(QueuedTaskLogMixin):
    class Meta: # type: ignore
        abstract = True
        default_order_by: OrderByList = [("logged_at", "desc")]
