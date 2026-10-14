# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
from collections.abc import Collection
from typing import Any

import sqlalchemy

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.depends.security import find_workspace_user_model
from fastedgy.http import Request
from fastedgy.orm.filter import And, R

logger = logging.getLogger("fastedgy.realtime.access")


async def readers(model_cls: Any, record_id: Any, scope_id: int, user_ids: Collection[int] | None = None) -> set[int]:
    """The members of a scope who can read one of its records.

    Each is asked the way a request of theirs would ask: as that account, in that
    scope, with that membership, through the model's scoped manager and so through
    its global filters and access guards. [user_ids] narrows who is asked, to the
    accounts a worker holds a socket for.
    """
    scope_user_model: Any = find_workspace_user_model()

    if scope_user_model is None or (user_ids is not None and not user_ids):
        return set()

    rule = R("workspace", "=", scope_id)

    if user_ids is not None:
        rule = And(rule, R("user", "in", sorted(user_ids)))

    memberships = await scope_user_model.in_effect().select_related("user", "workspace").filter(rule).all()
    questions: dict[int, Any] = {}

    for membership in memberships:
        user = getattr(membership, "user", None)

        if user is None:
            continue

        # A task of its own: the account it asks as never reaches the caller's context.
        question = await asyncio.create_task(_question(model_cls, record_id, user, membership.workspace, membership))

        if question is not None:
            questions[user.id] = question

    return await _ask(model_cls, questions)


async def _question(
    model_cls: Any,
    record_id: Any,
    user: Any,
    workspace: Any,
    workspace_user: Any,
    **params: Any,
) -> Any:
    """The statement asking whether one account reads a record, built as that account.

    Building it runs the model's global filters and access guards for that
    account, and asks the database nothing: a refusal answers here, as None.
    """
    token = context.set_request(
        Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})
    )

    try:
        context.set_user(user)
        context.set_workspace(workspace)
        context.set_workspace_user(workspace_user)

        with context.params(**params):
            return await model_cls.query.filter(R("id", "=", record_id)).as_select()
    except Exception as e:  # noqa: BLE001 - a refusal, or a rule that cannot be built, reads as no
        logger.debug("%s %s is not read by user %s: %s", model_cls.__name__, record_id, getattr(user, "id", None), e)

        return None
    finally:
        context.reset_request(token)


async def _ask(model_cls: Any, questions: dict[int, Any]) -> set[int]:
    """Put the questions of several accounts to the database in one statement."""
    if not questions:
        return set()

    accounts = list(questions)
    statement = sqlalchemy.select(
        *(questions[account].exists().label(f"reads_{index}") for index, account in enumerate(accounts))
    )
    row = await model_cls.meta.registry.database.fetch_one(statement)

    return {account for index, account in enumerate(accounts) if row is not None and row[index]}


def is_shared(model_cls: type) -> bool:
    """Whether a model hangs off a workspace-shareable root, and so is read from other scopes too."""
    from fastedgy.orm.workspace_shareable import WorkspaceShareableRegistry

    return get_service(WorkspaceShareableRegistry).has_paths(model_cls)


async def shared_readers(model_cls: Any, model_instance: Any, scope_id: int) -> set[int]:
    """The accounts outside a record's scope who read it through a shared root.

    A record under a workspace-shareable root, a task of a project for one, is read
    too by the members of that root from their own scope, through the shared-record
    context. Each member outside the record's scope is asked the way that context
    asks: the root's `workspace_shareable_authorize`, then the record, read as the
    root's workspace with the confinement filters armed. The members of the scope
    are not asked: the scope's own announcement reaches them.
    """
    from fastedgy.orm.workspace_shareable import WorkspaceShareableRegistry, resolve_workspace_shared_record

    record_id = getattr(model_instance, "id", None)
    scope_user_model: Any = find_workspace_user_model()
    registry = get_service(WorkspaceShareableRegistry)
    found: set[int] = set()
    insiders: set[Any] | None = None

    if record_id is None or scope_user_model is None:
        return found

    for root in registry.roots().values():
        if root.member_model is None or registry.path_for(model_cls, root.key) is None:
            continue

        shared = await resolve_workspace_shared_record(model_instance, root.key)

        if shared is None:
            continue

        if insiders is None:
            users = (
                await scope_user_model.in_effect().filter(R("workspace", "=", scope_id)).values_list("user", flat=True)
            )
            insiders = {_id(user) for user in users}

        workspace = await _workspace_of(root.root_model, shared)
        authorize = getattr(root.root_model, "workspace_shareable_authorize", None)
        member_model: Any = root.member_model
        members = (
            await member_model.global_query.select_related(root.member_user_field)
            .filter(R(root.member_record_field, "=", shared.pk))
            .all()
        )
        questions: dict[int, Any] = {}

        for member in members:
            user = getattr(member, root.member_user_field, None)
            user_id = getattr(user, "id", None)

            if user_id is None or user_id in insiders or user_id in found or user_id in questions:
                continue

            if authorize is not None and not await authorize(shared, user, member):
                continue

            question = await asyncio.create_task(
                _question(
                    model_cls,
                    record_id,
                    user,
                    workspace,
                    None,
                    workspace_shared_record=(root.key, shared.pk),
                    workspace_shared_record_member=member,
                    workspace_shared_record_instance=shared,
                )
            )

            if question is not None:
                questions[user_id] = question

        found |= await _ask(model_cls, questions)

    return found


async def _workspace_of(root_model: Any, shared: Any) -> Any:
    """The workspace a shared record lives in, loaded as the shared-record context loads it."""
    workspace_model = getattr(root_model.meta.fields.get("workspace"), "target", None)
    workspace_pk = getattr(getattr(shared, "workspace", None), "pk", None)

    if not isinstance(workspace_model, type) or workspace_pk is None:
        return None

    return await workspace_model.global_query.filter(R("id", "=", workspace_pk)).first()


def _id(value: Any) -> Any:
    return value.get("id") if isinstance(value, dict) else getattr(value, "id", value)


__all__ = [
    "is_shared",
    "readers",
    "shared_readers",
]
