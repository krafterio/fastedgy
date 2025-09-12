# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Union

from edgy import fields
from enum import Enum

from fastedgy.models.base import BaseModel


if TYPE_CHECKING:
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.user import BaseUser as User


class BaseWorkspaceUser(BaseModel):
    """Model for managing workspace users and their roles"""

    class Meta:
        abstract = True
        label = "Utilisateur de l'espace de travail"
        label_plural = "Utilisateurs de l'espace de travail"
        unique_together = [("workspace", "user")]

    workspace: Union["Workspace", None] = fields.ForeignKey('Workspace', on_delete='CASCADE', related_name='workspace_users', label="Espace de travail") # type: ignore
    user: Union["User", None] = fields.ForeignKey('User', on_delete='CASCADE', related_name='workspace_memberships', label="Utilisateur") # type: ignore


__all__ = [
    "BaseWorkspaceUser",
]
