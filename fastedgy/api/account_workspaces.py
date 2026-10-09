# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The workspaces of the signed-in account, read the way any generated list reads.

A workspace belongs to its members: what the account sees of one is its
membership, with the workspace under it and what only the account knows of it
(its default, the order it gave them, its role). The list is read from the
memberships of the account, so the default comes first, then the order the
membership model declares (``sequence``, when it has one), then the name, and
each item is the workspace with those fields beside its own.

The list is a generated list in every respect (pagination, ``X-Fields``,
``X-Filter``, ``order_by``) over the fields of the workspace: a path the
membership does not hold reads through its workspace (``name`` is
``workspace.name``). A name neither of them holds stays as asked, for a view
transformer of the membership to serve (a count, a flag): it finds it in
``ctx["fields"]``, as in any list.
"""

from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from fastedgy.api_route_model.actions.list_action import list_items_action
from fastedgy.api_route_model.params import FieldSelectorHeader, FilterHeader, OrderByQuery
from fastedgy.api_route_model.view_transformer import BaseViewTransformer
from fastedgy.depends.security import find_workspace_user_model, get_current_user
from fastedgy.http import Request
from fastedgy.orm.filter import R
from fastedgy.orm.filter.builder import filter_query
from fastedgy.orm.filter.parser import parse_filter_input
from fastedgy.orm.filter.types import FilterCondition, FilterRule, InvalidFilterError
from fastedgy.orm.query import QuerySet

type AccountMemberships = Callable[[Any], QuerySet | Coroutine[Any, Any, QuerySet]]

_WORKSPACE = "workspace"


def account_memberships(user: Any) -> QuerySet:
    """The memberships of [user] in effect, every workspace it belongs to."""
    model = _membership_model()

    return model.in_effect(model.query).filter(R("user", "=", user.id))


def _membership_model() -> Any:
    model = find_workspace_user_model()

    if model is None:
        raise RuntimeError("No workspace user model is registered")

    return model


def _workspace_model(membership: Any) -> Any:
    return membership.meta.fields[_WORKSPACE].target


def _own_fields(membership: Any) -> frozenset[str]:
    """What the membership holds that the workspace does not: its default, its
    order, its role. A name both hold is the workspace's (``id``)."""
    workspace = _workspace_model(membership)

    return frozenset(
        name
        for name, field in membership.meta.fields.items()
        if name not in (_WORKSPACE, "user")
        and name not in workspace.meta.fields
        and not getattr(field, "exclude", False)
        and not getattr(field, "secret", False)
        and not hasattr(field, "target")
        and not hasattr(field, "related_from")
    )


def _plain_fields(model: Any) -> list[str]:
    return [
        name
        for name, field in model.meta.fields.items()
        if not getattr(field, "exclude", False)
        and not getattr(field, "secret", False)
        and not hasattr(field, "target")
        and not hasattr(field, "related_from")
        and not getattr(field, "is_m2m", False)
    ]


def _workspace_names(membership: Any) -> frozenset[str]:
    workspace = _workspace_model(membership)

    return frozenset(workspace.meta.fields) | frozenset(getattr(workspace, "model_computed_fields", {}))


def _through_workspace(path: str, own: frozenset[str], workspace: frozenset[str]) -> str:
    head = path.split(".", 1)[0]

    return f"{_WORKSPACE}.{path}" if head not in own and head in workspace else path


def _fields(fields: str | None, membership: Any, own: frozenset[str], workspace: frozenset[str]) -> str:
    asked = [part.strip() for part in (fields or "").split(",") if part.strip() and part.strip() != "+"]

    if not asked:
        asked = _plain_fields(_workspace_model(membership))

    return ",".join(sorted(own) + [_through_workspace(path, own, workspace) for path in asked])


def _order_by(order_by: str | None, own: frozenset[str], workspace: frozenset[str]) -> str:
    """In the format of every list (``name:asc,created_at:desc``), each path
    read through the workspace when the membership does not hold it."""
    if not order_by:
        default = ["is_default:desc"] if "is_default" in own else []

        if "sequence" in own:
            default.append("sequence:asc")

        return ",".join([*default, f"{_WORKSPACE}.name:asc"])

    terms = []

    for term in (one.strip() for one in order_by.split(",")):
        if term:
            path, _, direction = term.partition(":")
            terms.append(_through_workspace(path, own, workspace) + (f":{direction}" if direction else ""))

    return ",".join(terms)


def _rule(
    rule: FilterRule | FilterCondition, own: frozenset[str], workspace: frozenset[str]
) -> FilterRule | FilterCondition:
    """The same rule, its paths read through the workspace. What an ``any``
    block holds is relative to the relation it names, and stays as it is."""
    if isinstance(rule, FilterCondition):
        return FilterCondition(condition=rule.condition, rules=[_rule(one, own, workspace) for one in rule.rules])

    return R(_through_workspace(rule.field, own, workspace), rule.operator, rule.value)


def _flatten(item: dict[str, Any]) -> dict[str, Any]:
    """The workspace, with what the membership carries beside it: its own
    fields and whatever a view transformer added."""
    workspace = item.get(_WORKSPACE)
    beside = {name: value for name, value in item.items() if name not in (_WORKSPACE, "user", "id")}

    return {**(workspace if isinstance(workspace, dict) else {}), **beside}


def create_account_workspaces_router(
    prefix: str = "/workspaces",
    memberships: AccountMemberships = account_memberships,
    transformers: list[type[BaseViewTransformer]] | None = None,
) -> APIRouter:
    """Built at wiring time, not at import: the concrete membership model only
    exists once the registry is up. Mounted on the router of the account, next
    to ``/me``; ``memberships`` replaces the query the list starts from, for an
    application that counts only some (an active status). ``transformers`` are
    view transformers of the membership model run for this list only: what one
    adds to a membership (whether the account owns the workspace) goes beside
    the fields of the workspace, and a name it serves is in ``ctx["fields"]``
    when the client asked for it."""
    router = APIRouter(prefix=prefix, tags=["workspaces"])

    async def memberships_of(user: Any) -> QuerySet:
        query = memberships(user)

        return await query if isinstance(query, Coroutine) else query

    @router.get("")
    async def list_account_workspaces(
        request: Request,
        limit: int = Query(50, ge=0, le=1000),
        offset: int = Query(0, ge=0),
        order_by: str | None = OrderByQuery(),
        fields: str | None = FieldSelectorHeader(),
        filters: str | None = FilterHeader(),
        current_user=Depends(get_current_user),
    ) -> dict[str, Any]:
        membership = _membership_model()
        own = _own_fields(membership)
        workspace = _workspace_names(membership)
        query = await memberships_of(current_user)

        try:
            condition = parse_filter_input(filters)
        except InvalidFilterError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error

        if condition is not None:
            query = filter_query(query, cast(FilterCondition, _rule(condition, own, workspace)))

        page = await list_items_action(
            request,
            membership,
            query,
            limit=limit,
            offset=offset,
            order_by=_order_by(order_by, own, workspace),
            fields=_fields(fields, membership, own, workspace),
            transformers=transformers,
        )

        return {
            "items": [_flatten(cast(dict[str, Any], item)) for item in page.items],
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
        }

    @router.put("/{slug}/default", status_code=status.HTTP_204_NO_CONTENT)
    async def make_default_workspace(slug: str, current_user=Depends(get_current_user)) -> Response:
        """The membership of [slug] among those the list reads."""
        query = await memberships_of(current_user)
        found: Any = await query.select_related(_WORKSPACE).filter(R(f"{_WORKSPACE}.slug", "=", slug)).first()

        if found is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_member")

        await found.make_default()

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


__all__ = [
    "AccountMemberships",
    "account_memberships",
    "create_account_workspaces_router",
]
