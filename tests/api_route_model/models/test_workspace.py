# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


# --- create -----------------------------------------------------------------


async def test_create_returns_workspace(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.post("/api/workspaces", json={"slug": "acme", "name": "Acme"})

    assert response.status_code == 200

    item = response.json()

    assert item["id"]
    assert item["slug"] == "acme"
    assert item["name"] == "Acme"
    assert set(item) >= {"id", "slug", "name", "image_url", "created_at", "updated_at"}


async def test_create_without_slug_is_rejected(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.post("/api/workspaces", json={"name": "No slug"})

    assert response.status_code == 422


async def test_create_with_duplicate_slug_is_rejected(setup_http: httpx.AsyncClient) -> None:
    await setup_http.post("/api/workspaces", json={"slug": "acme"})

    response = await setup_http.post("/api/workspaces", json={"slug": "acme"})

    assert response.status_code == 400


# --- get --------------------------------------------------------------------


async def test_get_returns_workspace(setup_http: httpx.AsyncClient) -> None:
    created = (await setup_http.post("/api/workspaces", json={"slug": "acme", "name": "Acme"})).json()

    response = await setup_http.get(f"/api/workspaces/{created['id']}")

    assert response.status_code == 200
    assert response.json()["slug"] == "acme"


async def test_get_unknown_workspace_returns_404(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.get("/api/workspaces/999999")

    assert response.status_code == 404


# --- list -------------------------------------------------------------------


async def test_list_uses_default_ordering_by_name(setup_http: httpx.AsyncClient) -> None:
    await setup_http.post("/api/workspaces", json={"slug": "s1", "name": "Charlie"})
    await setup_http.post("/api/workspaces", json={"slug": "s2", "name": "Alpha"})
    await setup_http.post("/api/workspaces", json={"slug": "s3", "name": "Bravo"})

    payload = (await setup_http.get("/api/workspaces")).json()

    assert payload["total"] == 3
    assert [item["name"] for item in payload["items"]] == ["Alpha", "Bravo", "Charlie"]


# --- patch ------------------------------------------------------------------


async def test_patch_updates_name(setup_http: httpx.AsyncClient) -> None:
    created = (await setup_http.post("/api/workspaces", json={"slug": "acme", "name": "Old"})).json()

    response = await setup_http.patch(f"/api/workspaces/{created['id']}", json={"name": "New"})

    assert response.status_code == 200

    item = response.json()

    assert item["name"] == "New"
    assert item["slug"] == "acme"


# --- delete -----------------------------------------------------------------


async def test_delete_removes_workspace(setup_http: httpx.AsyncClient) -> None:
    created = (await setup_http.post("/api/workspaces", json={"slug": "acme"})).json()

    response = await setup_http.delete(f"/api/workspaces/{created['id']}")

    assert response.status_code in (200, 204)
    assert (await setup_http.get(f"/api/workspaces/{created['id']}")).status_code == 404
