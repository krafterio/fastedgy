# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Union

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel


if TYPE_CHECKING:
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.user import BaseUser as User


class BaseWorkspaceUser(BaseModel):
    """Model for managing workspace users and their roles"""

    class Meta(BaseModel.Meta):
        abstract = True
        label = "Utilisateur de l'espace de travail"
        label_plural = "Utilisateurs de l'espace de travail"
        unique_together = [("workspace", "user")]
        model_name: str | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        meta = getattr(cls, "Meta", None)
        if not meta or getattr(meta, "abstract", False):
            return

        if BaseWorkspaceUser.Meta.model_name is None:
            BaseWorkspaceUser.Meta.model_name = cls.__name__
            return

        if BaseWorkspaceUser.Meta.model_name == cls.__name__:
            return

        raise RuntimeError(
            f"Multiple workspace user models detected: "
            f"{BaseWorkspaceUser.Meta.model_name} and {cls.__name__}"
        )

    workspace: Union["Workspace", None] = fields.ForeignKey(
        "Workspace",
        on_delete="CASCADE",
        related_name="workspace_users",
        label="Espace de travail",
    )  # type: ignore
    user: Union["User", None] = fields.ForeignKey(
        "User",
        on_delete="CASCADE",
        related_name="workspace_memberships",
        label="Utilisateur",
    )  # type: ignore


__all__ = [
    "BaseWorkspaceUser",
]
