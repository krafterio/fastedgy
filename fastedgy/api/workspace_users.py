# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The users of the current workspace, read the way any generated list reads.

A relation to the user model (an owner, an assignee) needs its records listed
and searched from inside a workspace, and the user model has no route of its
own there: it belongs to every workspace at once. These routes serve its
members only, through the generated list and get actions, so pagination,
ordering, field selection and filters behave as on every other model.
"""

from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import APIRouter, Depends, Path, Query

from fastedgy.api_route_model.actions.get_action import get_item_action
from fastedgy.api_route_model.actions.list_action import list_items_action
from fastedgy.api_route_model.params import (
    FieldSelectorHeader,
    FilterHeader,
    OrderByQuery,
)
from fastedgy.api_route_model.types import ModelItem, ModelList
from fastedgy.dependencies import get_service
from fastedgy.depends.security import get_current_workspace
from fastedgy.http import Request
from fastedgy.models.user import BaseUser
from fastedgy.orm import Registry
from fastedgy.orm.filter import R
from fastedgy.orm.query import QuerySet
from fastedgy.schemas import ErrorMessage

type WorkspaceMembers = Callable[[Any], QuerySet | Coroutine[Any, Any, QuerySet]]


def _user_model() -> type[BaseUser]:
    return cast(type[BaseUser], get_service(Registry).get_model(BaseUser.Meta.model_name or "User"))


def workspace_members(workspace: Any) -> QuerySet:
    """The users holding a membership of the workspace, through the relation
    every workspace user model declares."""
    return _user_model().query.filter(
        R("workspace_memberships.workspace", "=", workspace.id),
        allow_excluded=True,
    )


def create_workspace_users_router(
    prefix: str = "/users",
    members: WorkspaceMembers = workspace_members,
) -> APIRouter:
    """Built at wiring time, not at import: the concrete user model only exists
    once the registry is up. Mounted on the router that resolves the workspace,
    next to the generated routes; ``members`` replaces the query the routes
    start from, for an application that serves more than the memberships."""
    User = _user_model()
    router = APIRouter(prefix=prefix, tags=["users"])

    async def members_of(workspace: Any) -> QuerySet:
        query = members(workspace)

        return await query if isinstance(query, Coroutine) else query

    @router.get("", response_model=ModelList[User])
    async def list_workspace_users(
        request: Request,
        limit: int = Query(50, ge=0, le=1000),
        offset: int = Query(0, ge=0),
        order_by: str | None = OrderByQuery(),
        fields: str | None = FieldSelectorHeader(),
        filters: str | None = FilterHeader(),
        workspace=Depends(get_current_workspace),
    ):
        return await list_items_action(
            request,
            User,
            query=await members_of(workspace),
            limit=limit,
            offset=offset,
            order_by=order_by,
            fields=fields,
            filters=filters,
        )

    @router.get(
        "/{item_id}",
        response_model=ModelItem[User],
        responses={404: {"model": ErrorMessage, "description": "Item not found"}},
    )
    async def get_workspace_user(
        request: Request,
        item_id: int = Path(..., description="Item ID"),
        fields: str | None = FieldSelectorHeader(),
        workspace=Depends(get_current_workspace),
    ):
        return await get_item_action(request, User, item_id, await members_of(workspace), fields=fields)

    return router


__all__ = [
    "WorkspaceMembers",
    "create_workspace_users_router",
    "workspace_members",
]
