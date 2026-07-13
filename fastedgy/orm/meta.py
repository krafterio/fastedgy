# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy import Model

from fastedgy.orm.order_by import OrderByList


class Meta(Model.Meta):
    tablename: str
    label: str
    label_plural: str
    model_name: str | None
    default_order_by: OrderByList
    sortable_field: str | None
    search_field: str | None
    workspace_preserve_explicit: bool
    workspace_filter: bool
    workspace_shareable_record_field: str
    workspace_shareable_user_field: str
    global_storage: bool
    is_view: bool


__all__ = [
    "Meta",
]
