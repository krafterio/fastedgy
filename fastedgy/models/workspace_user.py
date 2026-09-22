# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Self

from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.orm.filter import And, Or, R
from fastedgy.orm.transaction import with_transaction

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

    is_default: bool = fields.BooleanField(
        default=False,
        read_only=True,
        label=_ts("Default workspace"),
    )

    @classmethod
    async def default_for(cls, user_id: int) -> Self | None:
        """The membership a user lands in: the one marked as default, the oldest otherwise.

        The oldest stands for a mark nobody set, or one that went with its row, a
        database cascade included: a user holding a membership always has one."""
        return await (
            cls.global_query.select_related("workspace")
            .filter(R("user", "=", user_id))
            .order_by("-is_default", "id")
            .first()
        )

    async def make_default(self) -> None:
        """Mark this membership as its user's default, and no other.

        The rows are read again rather than saved from this instance, which may
        hold only some of its fields, and keeps the mark it had in memory."""
        model = type(self)
        user_id = getattr(getattr(self, "user", None), "id", None)

        async def _mark() -> None:
            memberships = await model.global_query.filter(
                And(R("user", "=", user_id), Or(R("is_default", "is true"), R("id", "=", self.id)))
            ).all()

            for membership in memberships:
                membership.apply_readonly_values({"is_default": membership.id == self.id})
                await membership.save()

        await with_transaction(_mark)


__all__ = [
    "BaseWorkspaceUser",
]
