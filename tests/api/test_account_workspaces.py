# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import APIRouter, Depends

from fastedgy.api.account_workspaces import account_memberships, create_account_workspaces_router
from fastedgy.api_route_model.view_transformer import GetViewTransformer
from fastedgy.app import FastEdgy
from fastedgy.depends.security import get_current_user
from fastedgy.orm.field_selector import selection_includes
from fastedgy.orm.filter import R
from fastedgy.test.factories import authenticate, create_user, create_workspace, create_workspace_user

URL = "/api/workspaces"


class _Mine(GetViewTransformer):
    """What an application computes for the account, beside the membership."""

    async def get_view(self, request, item, item_dump, ctx):
        return {**item_dump, "mine": True}


class _Count(GetViewTransformer):
    """What an application computes only when the client asks for it by name."""

    async def get_view(self, request, item, item_dump, ctx):
        return {**item_dump, "count": 1} if selection_includes(ctx.get("fields"), "count") else item_dump


@pytest.fixture
async def account_http(setup_db: FastEdgy, setup_http: httpx.AsyncClient) -> AsyncIterator[httpx.AsyncClient]:
    """The routes mounted as an application mounts them, at /api/workspaces: ahead
    of the generated routes the synthetic workspace model has there."""
    router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
    router.include_router(create_account_workspaces_router(transformers=[_Mine, _Count]))
    routes = list(router.routes)
    setup_db.router.routes[0:0] = routes

    try:
        yield setup_http
    finally:
        for route in routes:
            setup_db.router.routes.remove(route)


async def _account():
    acme = await create_workspace(slug="acme", name="Acme")
    beta = await create_workspace(slug="beta", name="Beta")
    zeta = await create_workspace(slug="zeta", name="Zeta")
    other = await create_workspace(slug="other", name="Other")
    me = await create_user(email="me@example.io")
    stranger = await create_user(email="stranger@example.io")

    await create_workspace_user(me, acme)
    await create_workspace_user(me, beta)
    default = await create_workspace_user(me, zeta)
    await create_workspace_user(stranger, other)
    await create_workspace_user(stranger, acme)
    await default.make_default()

    return me


def _slugs(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text

    return [item["slug"] for item in response.json()["items"]]


async def test_lists_the_workspaces_of_the_account_its_default_first_then_by_name(
    account_http: httpx.AsyncClient,
) -> None:
    client = authenticate(account_http, await _account())

    response = await client.get(URL, headers={"X-Fields": "id,slug,name"})

    assert _slugs(response) == ["zeta", "acme", "beta"]
    assert response.json()["total"] == 3
    assert [item["is_default"] for item in response.json()["items"]] == [True, False, False]
    assert response.json()["items"][1]["name"] == "Acme"


async def test_pages_filters_and_orders_the_workspaces_like_any_list(account_http: httpx.AsyncClient) -> None:
    client = authenticate(account_http, await _account())

    paged = await client.get(URL, params={"limit": 1, "offset": 1}, headers={"X-Fields": "slug"})
    filtered = await client.get(URL, headers={"X-Fields": "slug", "X-Filter": json.dumps(["name", "icontains", "ET"])})
    ordered = await client.get(URL, params={"order_by": "name:desc"}, headers={"X-Fields": "slug"})

    assert _slugs(paged) == ["acme"]
    assert paged.json()["total"] == 3
    assert _slugs(filtered) == ["zeta", "beta"]
    assert _slugs(ordered) == ["zeta", "beta", "acme"]


async def test_reads_every_field_of_the_workspace_when_none_is_asked(account_http: httpx.AsyncClient) -> None:
    client = authenticate(account_http, await _account())

    item = (await client.get(URL)).json()["items"][0]

    assert {"id", "slug", "name", "is_default", "mine"} <= set(item)


async def test_changes_the_default_only_when_asked_to(account_http: httpx.AsyncClient) -> None:
    client = authenticate(account_http, await _account())

    response = await client.put(f"{URL}/acme/default")

    assert response.status_code == 204, response.text
    assert _slugs(await client.get(URL, headers={"X-Fields": "slug"})) == ["acme", "beta", "zeta"]
    assert (await client.put(f"{URL}/other/default")).status_code == 404


async def test_serves_a_name_neither_model_holds_only_when_it_is_asked(account_http: httpx.AsyncClient) -> None:
    client = authenticate(account_http, await _account())

    asked = (await client.get(URL, headers={"X-Fields": "slug,count"})).json()["items"]
    unasked = (await client.get(URL, headers={"X-Fields": "slug"})).json()["items"]

    assert [item["count"] for item in asked] == [1, 1, 1]
    assert all("count" not in item for item in unasked)


async def test_cannot_make_default_a_workspace_the_list_leaves_out(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient
) -> None:
    """An application counting only some memberships (an active status) lists
    none of the others, and none of them can become the default either."""

    def without_beta(user):
        return account_memberships(user).filter(R("workspace.slug", "!=", "beta"))

    router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
    router.include_router(create_account_workspaces_router(prefix="/listed", memberships=without_beta))
    routes = list(router.routes)
    setup_db.router.routes[0:0] = routes

    try:
        client = authenticate(setup_http, await _account())

        assert (await client.put("/api/listed/beta/default")).status_code == 404
        assert (await client.put("/api/listed/acme/default")).status_code == 204
    finally:
        for route in routes:
            setup_db.router.routes.remove(route)
