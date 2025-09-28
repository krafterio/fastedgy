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
    from fastedgy.models.workspace import BaseWorkspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser
    workspace_field = queryset.model_class.fields.get("workspace")

    if (
        workspace_field
        and isinstance(workspace_field, ForeignKey)
        and issubclass(workspace_field.target, BaseWorkspace)
    ):
        workspace = context.get_workspace()

        if (
            workspace and queryset.model_class.__name__ not in [
                "UserPresence",
            ]
            and not issubclass(queryset.model_class, BaseWorkspace)
            and not issubclass(queryset.model_class, BaseWorkspaceUser)
        ):
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
