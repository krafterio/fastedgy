# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.workspace_extra_field import BaseWorkspaceExtraField


@api_route_model()
class WorkspaceExtraField(BaseWorkspaceExtraField):
    class Meta(BaseWorkspaceExtraField.Meta):
        tablename = "workspace_extra_fields"


__all__ = [
    "WorkspaceExtraField",
]
