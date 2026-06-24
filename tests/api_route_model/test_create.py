# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from .helpers import get_product, make_category, make_product, make_tag, tag_ids


async def test_create_returns_item_with_defaults(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.post("/api/test_products", json={"name": "Widget", "price": "9.99"})

    assert response.status_code == 200

    item = response.json()

    assert item["id"]
    assert item["name"] == "Widget"
    assert item["price"] == "9.99"
    assert item["is_active"] is True
    assert item["quantity"] == 0


async def test_create_missing_required_field_is_rejected(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.post("/api/test_products", json={"name": "No price"})

    assert response.status_code == 422


async def test_create_with_foreign_key_id(setup_http: httpx.AsyncClient) -> None:
    category = await make_category(setup_http, "Electronics")

    product = await make_product(setup_http, category=category["id"])

    fetched = await get_product(setup_http, product["id"])

    assert fetched["category"]["id"] == category["id"]
    assert fetched["category"]["name"] == "Electronics"


async def test_create_with_many_to_many_simple_mode(setup_http: httpx.AsyncClient) -> None:
    t1 = await make_tag(setup_http, "a")
    t2 = await make_tag(setup_http, "b")

    product = await make_product(setup_http, tags=[t1["id"], t2["id"]])

    fetched = await get_product(setup_http, product["id"])

    assert tag_ids(fetched) == {t1["id"], t2["id"]}
