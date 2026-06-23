# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.models.workspace import BaseWorkspace
from fastedgy.api_route_model import api_route_model


@api_route_model()
class Workspace(BaseWorkspace):
    class Meta(BaseWorkspace.Meta):
        tablename = "workspaces"


__all__ = [
    "Workspace",
]
