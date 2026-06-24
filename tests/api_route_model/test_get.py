# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from .helpers import make_category, make_product, make_tag


async def test_get_returns_existing_item(auth_http: httpx.AsyncClient) -> None:
    created = (await auth_http.post("/api/test_categories", json={"name": "Books"})).json()

    response = await auth_http.get(f"/api/test_categories/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Books"


async def test_get_unknown_item_returns_404(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/test_categories/999999")

    assert response.status_code == 404


async def test_relations_are_excluded_from_default_payload(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Electronics")
    tag = await make_tag(auth_http, "a")

    product = await make_product(auth_http, category=category["id"], tags=[tag["id"]])

    fetched = (await auth_http.get(f"/api/test_products/{product['id']}")).json()

    # ForeignKey is serialized as a bare id reference, ManyToMany is not loaded.
    assert fetched["category"] == {"id": category["id"]}
    assert fetched.get("tags") is None


async def test_field_selection_loads_requested_relations(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Electronics")
    tag = await make_tag(auth_http, "a")
    product = await make_product(auth_http, category=category["id"], tags=[tag["id"]])

    fetched = (
        await auth_http.get(
            f"/api/test_products/{product['id']}",
            headers={"X-Fields": "name,category.name,tags.name"},
        )
    ).json()

    assert fetched["category"]["name"] == "Electronics"
    assert [item["name"] for item in fetched["tags"]] == ["a"]
