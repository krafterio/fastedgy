# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.api_route_model.params import OrderByList
from fastedgy.queued_task.models.queued_task import QueuedTaskMixin


@api_route_model(
    list=True,
    get=True,
    create=False,
    patch=False,
    delete=True,
    export=False,
)
class BaseQueuedTask(QueuedTaskMixin):
    class Meta: # type: ignore
        abstract = True
        default_order_by: OrderByList = [("date_enqueued", "desc"), ("state", "asc")]
