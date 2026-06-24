# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

import httpx

from .helpers import make_category, make_product


async def _seed_categories(client: httpx.AsyncClient, names: list[str]) -> list[dict]:
    created = []
    for name in names:
        created.append((await client.post("/api/test_categories", json={"name": name})).json())
    return created


async def test_list_metadata_shape(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["A", "B", "C"])

    payload = (await auth_http.get("/api/test_categories")).json()

    assert payload["total"] == 3
    assert len(payload["items"]) == 3
    assert set(payload) >= {"items", "total", "limit", "offset", "total_pages"}


async def test_list_pagination_limit_and_offset(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["A", "B", "C", "D", "E"])

    first = (await auth_http.get("/api/test_categories?limit=2&offset=0")).json()
    second = (await auth_http.get("/api/test_categories?limit=2&offset=2")).json()

    assert first["total"] == 5
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert first["total_pages"] == 3

    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}

    assert first_ids.isdisjoint(second_ids)


async def test_list_limit_zero_returns_count_only(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["A", "B", "C"])

    payload = (await auth_http.get("/api/test_categories?limit=0")).json()

    assert payload["total"] == 3
    assert payload["items"] == []


async def test_list_order_by_field(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["Charlie", "Alpha", "Bravo"])

    payload = (await auth_http.get("/api/test_categories?order_by=name")).json()

    names = [item["name"] for item in payload["items"]]

    assert names == ["Alpha", "Bravo", "Charlie"]


async def test_list_order_by_descending(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["Alpha", "Bravo", "Charlie"])

    payload = (await auth_http.get("/api/test_categories?order_by=name:desc")).json()

    names = [item["name"] for item in payload["items"]]

    assert names == ["Charlie", "Bravo", "Alpha"]


async def test_field_selection_limits_returned_fields(auth_http: httpx.AsyncClient) -> None:
    await auth_http.post("/api/test_categories", json={"name": "Books", "description": "hidden"})

    payload = (await auth_http.get("/api/test_categories", headers={"X-Fields": "name"})).json()

    item = payload["items"][0]

    assert item["name"] == "Books"
    assert "description" not in item


async def test_filter_by_field_equality(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["Books", "Movies", "Music"])

    payload = (
        await auth_http.get(
            "/api/test_categories",
            headers={"X-Filter": json.dumps(["name", "=", "Movies"])},
        )
    ).json()

    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Movies"


async def test_filter_by_related_field(auth_http: httpx.AsyncClient) -> None:
    electronics = await make_category(auth_http, "Electronics")
    books = await make_category(auth_http, "Books")
    await make_product(auth_http, name="Phone", category=electronics["id"])
    await make_product(auth_http, name="Novel", category=books["id"])

    payload = (
        await auth_http.get(
            "/api/test_products",
            headers={"X-Filter": json.dumps(["category.name", "=", "Books"])},
        )
    ).json()

    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Novel"
