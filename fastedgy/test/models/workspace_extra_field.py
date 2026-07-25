# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n import _ts
from fastedgy.models.workspace_extra_field import BaseWorkspaceExtraField
from fastedgy.orm import fields
from fastedgy.api_route_model import api_route_model


class WorkspaceExtraFieldModel(fields.ChoiceEnum):
    product = _ts("Product")


@api_route_model()
class WorkspaceExtraField(BaseWorkspaceExtraField):
    class Meta(BaseWorkspaceExtraField.Meta):
        tablename = "workspace_extra_fields"

    model: WorkspaceExtraFieldModel | None = fields.ChoiceField(
        WorkspaceExtraFieldModel,
        null=True,
        label=_ts("Model"),
    )


__all__ = [
    "WorkspaceExtraFieldModel",
    "WorkspaceExtraField",
]
