# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.workspace_user import BaseWorkspaceUser


@api_route_model()
class WorkspaceUser(BaseWorkspaceUser):
    class Meta(BaseWorkspaceUser.Meta):
        tablename = "workspace_users"


__all__ = [
    "WorkspaceUser",
]
