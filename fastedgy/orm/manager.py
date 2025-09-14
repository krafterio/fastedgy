# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.models.managers import Manager, RedirectManager, BaseManager

from fastedgy import context
from fastedgy.orm.query import QuerySet
from fastedgy.orm.fields import ForeignKey


class WorkspaceableManager(Manager):
    def get_queryset(self) -> QuerySet:
        return filter_by_workspace(super().get_queryset())


class WorkspaceableRedirectManager(RedirectManager):
    def get_queryset(self) -> QuerySet:
        return filter_by_workspace(super().get_queryset())


def filter_by_workspace(queryset: QuerySet) -> QuerySet:
    workspace_field = queryset.model_class.fields.get("workspace")

    if (
        workspace_field
        and isinstance(workspace_field, ForeignKey)
        and workspace_field.target.__name__ == "Workspace"
    ):
        workspace = context.get_workspace()

        if workspace and queryset.model_class.__name__ not in [
            "Workspace",
            "WorkspaceUser",
            "UserPresence",
        ]:
            queryset = queryset.filter(workspace=workspace)

    return queryset


__all__ = [
    "BaseManager",
    "Manager",
    "RedirectManager",
    "WorkspaceableManager",
    "WorkspaceableRedirectManager",
    "filter_by_workspace",
]
