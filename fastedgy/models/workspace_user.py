# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING

from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace


class BaseWorkspaceUser(BaseModel):
    """Model for managing workspace users and their roles"""

    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Workspace user")
        label_plural = _ts("Workspace users")
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
            f"Multiple workspace user models detected: {BaseWorkspaceUser.Meta.model_name} and {cls.__name__}"
        )

    # Immutable through the API and regular saves: a membership is never
    # re-pointed to another workspace/user. Code sets them at creation time
    # via ``apply_readonly_values`` (see BaseModel).
    workspace: "Workspace | None" = fields.ForeignKey(
        "Workspace",
        on_delete="CASCADE",
        related_name="workspace_users",
        read_only=True,
        label=_ts("Workspace"),
    )

    user: "User | None" = fields.ForeignKey(
        "User",
        on_delete="CASCADE",
        related_name="workspace_memberships",
        read_only=True,
        label=_ts("User"),
    )


__all__ = [
    "BaseWorkspaceUser",
]
