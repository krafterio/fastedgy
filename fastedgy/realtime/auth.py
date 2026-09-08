# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Any, cast

from fastedgy.depends.security import find_workspace_user_model, resolve_bearer_token
from fastedgy.orm.filter import And, R

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace


async def user_of_token(token: str) -> "User | None":
    """The account behind the bearer a socket announced itself with.

    The same resolution every HTTP route uses, so a personal API key opens a
    socket exactly where it opens a route: an agent watching what it writes is
    the point of the channel, not an afterthought.
    """
    return await resolve_bearer_token(token)


async def workspace_of(user: "User", slug: Any) -> "Workspace | None":
    """The workspace behind a slug, if this account is a member of it.

    Membership is read the way `get_current_workspace` reads it, so a socket
    reaches exactly the workspaces its holder's requests reach, and no more.
    """
    if not slug or not isinstance(slug, str):
        return None

    WorkspaceUser = find_workspace_user_model()

    if WorkspaceUser is None:
        return None

    # Unscoped: a socket carries no request, so none of the context the scoped
    # manager reads is set.
    membership = (
        await WorkspaceUser.global_query.select_related("workspace")
        .filter(And(R("user", "=", user.id), R("workspace.slug", "=", slug)))
        .first()
    )
    workspace = getattr(membership, "workspace", None) if membership else None

    return cast("Workspace | None", workspace)


__all__ = [
    "user_of_token",
    "workspace_of",
]
