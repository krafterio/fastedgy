# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_list_categories_is_empty(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/test_categories")

    assert response.status_code == 200

    payload = response.json()

    assert payload["items"] == []
    assert payload["total"] == 0
    assert set(payload) >= {"items", "total", "limit", "offset", "total_pages"}


async def test_users_standard_model_listable(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/users")

    assert response.status_code == 200

    payload = response.json()

    assert payload["total"] == 0
    assert set(payload) >= {"items", "total", "limit", "offset", "total_pages"}


async def test_create_workspace_standard_model(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/workspaces", json={"name": "Acme", "slug": "acme"})

    assert response.status_code == 200
    assert response.json()["slug"] == "acme"


async def test_create_product_with_relation_and_fulltext(client: httpx.AsyncClient) -> None:
    category = (await client.post("/api/test_categories", json={"name": "Books"})).json()

    response = await client.post(
        "/api/test_products",
        json={"name": "Clean Code", "description": "a handbook", "price": "42.50", "category": category["id"]},
    )

    assert response.status_code == 200

    product = response.json()

    assert product["id"]
    assert product["name"] == "Clean Code"

    listing = await client.get("/api/test_products")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1


async def test_queued_task_standard_model_listable(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/queued_tasks")

    assert response.status_code == 200
    assert response.json()["total"] == 0
