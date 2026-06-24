# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


# --- create -----------------------------------------------------------------


async def test_create_returns_attachment(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post("/api/attachments", json={"name": "root"})

    assert response.status_code == 200

    item = response.json()

    assert item["id"]
    assert item["name"] == "root"
    assert item["parent"] is None


async def test_create_without_name_is_rejected(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post("/api/attachments", json={})

    assert response.status_code == 422


# --- self relation (parent / children) --------------------------------------


async def test_create_child_links_parent(auth_http: httpx.AsyncClient) -> None:
    root = (await auth_http.post("/api/attachments", json={"name": "root", "type": "folder"})).json()

    child = await auth_http.post("/api/attachments", json={"name": "child", "parent": root["id"]})

    assert child.status_code == 200
    assert child.json()["parent"] == {"id": root["id"]}


async def test_child_exposes_parent_via_field_selection(auth_http: httpx.AsyncClient) -> None:
    root = (await auth_http.post("/api/attachments", json={"name": "root", "type": "folder"})).json()
    child = (await auth_http.post("/api/attachments", json={"name": "child", "parent": root["id"]})).json()

    fetched = (await auth_http.get(f"/api/attachments/{child['id']}", headers={"X-Fields": "name,parent.name"})).json()

    assert fetched["parent"] == {"id": root["id"], "name": "root"}


async def test_parent_exposes_children_via_field_selection(auth_http: httpx.AsyncClient) -> None:
    root = (await auth_http.post("/api/attachments", json={"name": "root", "type": "folder"})).json()
    await auth_http.post("/api/attachments", json={"name": "child", "parent": root["id"]})

    fetched = (await auth_http.get(f"/api/attachments/{root['id']}", headers={"X-Fields": "name,children.name"})).json()

    assert [child["name"] for child in fetched["children"]] == ["child"]


# --- get / list / patch / delete --------------------------------------------


async def test_get_unknown_attachment_returns_404(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/attachments/999999")

    assert response.status_code == 404


async def test_list_returns_attachments(auth_http: httpx.AsyncClient) -> None:
    await auth_http.post("/api/attachments", json={"name": "a"})
    await auth_http.post("/api/attachments", json={"name": "b"})

    payload = (await auth_http.get("/api/attachments")).json()

    assert payload["total"] == 2


async def test_patch_updates_name(auth_http: httpx.AsyncClient) -> None:
    created = (await auth_http.post("/api/attachments", json={"name": "old"})).json()

    response = await auth_http.patch(f"/api/attachments/{created['id']}", json={"name": "new"})

    assert response.status_code == 200
    assert response.json()["name"] == "new"


async def test_delete_removes_attachment(auth_http: httpx.AsyncClient) -> None:
    created = (await auth_http.post("/api/attachments", json={"name": "temp"})).json()

    response = await auth_http.delete(f"/api/attachments/{created['id']}")

    assert response.status_code in (200, 204)
    assert (await auth_http.get(f"/api/attachments/{created['id']}")).status_code == 404
