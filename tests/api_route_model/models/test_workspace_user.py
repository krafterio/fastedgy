# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from ..helpers import seed_user


async def _make_workspace(client: httpx.AsyncClient, slug: str = "acme") -> dict:
    return (await client.post("/api/workspaces", json={"slug": slug})).json()


# --- create -----------------------------------------------------------------


async def test_create_links_workspace_and_user(setup_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(setup_http)
    user = await seed_user()

    response = await setup_http.post(
        "/api/workspace_users",
        json={"workspace": workspace["id"], "user": user.id},
    )

    assert response.status_code == 200

    item = response.json()

    assert item["workspace"] == {"id": workspace["id"]}
    assert item["user"] == {"id": user.id}


async def test_create_requires_both_foreign_keys(setup_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(setup_http)

    response = await setup_http.post("/api/workspace_users", json={"workspace": workspace["id"]})

    assert response.status_code == 422


async def test_duplicate_pair_is_rejected(setup_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(setup_http)
    user = await seed_user()
    payload = {"workspace": workspace["id"], "user": user.id}

    await setup_http.post("/api/workspace_users", json=payload)
    response = await setup_http.post("/api/workspace_users", json=payload)

    assert response.status_code == 400


# --- get / delete -----------------------------------------------------------


async def test_get_returns_membership(setup_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(setup_http)
    user = await seed_user()
    created = (
        await setup_http.post("/api/workspace_users", json={"workspace": workspace["id"], "user": user.id})
    ).json()

    response = await setup_http.get(f"/api/workspace_users/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_delete_removes_membership(setup_http: httpx.AsyncClient) -> None:
    workspace = await _make_workspace(setup_http)
    user = await seed_user()
    created = (
        await setup_http.post("/api/workspace_users", json={"workspace": workspace["id"], "user": user.id})
    ).json()

    response = await setup_http.delete(f"/api/workspace_users/{created['id']}")

    assert response.status_code in (200, 204)
    assert (await setup_http.get(f"/api/workspace_users/{created['id']}")).status_code == 404
