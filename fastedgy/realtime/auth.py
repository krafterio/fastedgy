# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Collection
from typing import TYPE_CHECKING, Any, cast

from fastedgy.depends.security import find_workspace_user_model, resolve_bearer_token
from fastedgy.orm.filter import And, R
from fastedgy.realtime.access import is_guarded, readers

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Scope


async def user_of_token(token: str) -> "User | None":
    """The account behind the bearer a socket announced itself with.

    The same resolution every HTTP route uses, so a personal API key opens a
    socket exactly where it opens a route: an agent watching what it writes is
    the point of the channel, not an afterthought.
    """
    return await resolve_bearer_token(token)


async def scope_of(user: "User", slug: Any) -> "Scope | None":
    """The scope behind a slug, if this account is a member of it.

    Membership is read the way an HTTP route reads it, so a socket reaches exactly
    the scopes its holder's requests reach, and no more.
    """
    if not slug or not isinstance(slug, str):
        return None

    scope_user_model = find_workspace_user_model()

    if scope_user_model is None:
        return None

    # Unscoped: a socket carries no request, so none of the context the scoped
    # manager reads is set.
    scope_user = (
        await scope_user_model.global_query.select_related("workspace")
        .filter(And(R("user", "=", user.id), R("workspace.slug", "=", slug)))
        .first()
    )

    return cast("Scope | None", getattr(scope_user, "workspace", None))


async def scopes_of(user: "User", slugs: Collection[Any]) -> "list[Scope]":
    """The scopes behind a list of slugs, those this account is a member of.

    One read for them all, however many the client sent. A slug the account is
    not a member of is left out rather than refused.
    """
    names = [slug for slug in slugs if slug and isinstance(slug, str)]
    scope_user_model = find_workspace_user_model()

    if not names or scope_user_model is None:
        return []

    scope_users = (
        await scope_user_model.global_query.select_related("workspace")
        .filter(And(R("user", "=", user.id), R("workspace.slug", "in", names)))
        .all()
    )

    return [cast("Scope", scope_user.workspace) for scope_user in scope_users if scope_user.workspace is not None]


async def held_scopes(user: "User", scope_ids: Collection[int]) -> set[int]:
    """Which of these scopes this account is still a member of.

    Read by id rather than by slug: a scope renamed while a socket reads it is
    still the scope that socket was let into.
    """
    scope_user_model = find_workspace_user_model()

    if not scope_ids or scope_user_model is None:
        return set()

    scope_users = await scope_user_model.global_query.filter(
        And(R("user", "=", user.id), R("workspace", "in", list(scope_ids)))
    ).all()

    return {
        scope_user.workspace.id
        for scope_user in scope_users
        if scope_user.workspace is not None and scope_user.workspace.id is not None
    }


class RealtimeAuth:
    """Who a socket is, what it reads, and who hears what is announced.

    A service an application replaces through DI when it reads any of it its own
    way.
    """

    async def user_of_token(self, token: str) -> "User | None":
        return await user_of_token(token)

    async def scope_of(self, user: "User", scope: Any) -> "Scope | None":
        return await scope_of(user, scope)

    async def scopes_of(self, user: "User", asked: Any) -> "list[Scope]":
        """The scopes a socket reads: each one of a list, or the one [scope_of] answers."""
        if isinstance(asked, list):
            return await scopes_of(user, asked)

        scope = await self.scope_of(user, asked)

        return [scope] if scope is not None else []

    async def held_scopes(self, user: "User", scope_ids: Collection[int]) -> set[int]:
        return await held_scopes(user, scope_ids)

    async def audience(
        self,
        scope_id: int,
        event_type: str,
        data: Any,
        user_ids: set[int],
        about: tuple[type, Any] | None = None,
    ) -> Collection[int]:
        """Who of these accounts may hear an event published to a scope.

        [user_ids] are the accounts a worker would deliver it to, [about] the model
        and the id of the record the event names, when it names one. An event about
        a record of a guarded model reaches the members who can read that record,
        any other event reaches them all. An application narrows its own events by
        replacing this, and keeps the rest through `super()`.
        """
        if about is not None and is_guarded(about[0]):
            return await readers(about[0], about[1], scope_id, user_ids)

        return user_ids

    async def recipients(self, event_type: str, data: Any, user_ids: set[int]) -> Collection[int]:
        """Who hears a write of a model addressed to accounts.

        [user_ids] are the accounts the model's `user_field` names, [data] what the
        event carries: the model, the id and the declared columns. They alone hear
        it by default. An application widens or narrows who does by replacing this,
        and keeps the rest through `super()`. It is asked by the process that
        writes: before the row goes for a deletion, once the write is committed
        otherwise.
        """
        return user_ids


__all__ = [
    "RealtimeAuth",
    "held_scopes",
    "scope_of",
    "scopes_of",
    "user_of_token",
]
