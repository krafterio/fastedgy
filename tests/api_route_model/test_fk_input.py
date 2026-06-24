# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.relations.processor import process_foreign_key_operation
from fastedgy.orm.relations.utils import RelationOperationError

from fastedgy.test.models.category import Category


async def _make_category(http: httpx.AsyncClient, name: str) -> dict:
    return (await http.post("/api/test_categories", json={"name": name})).json()


async def _create_product(http: httpx.AsyncClient, **extra) -> httpx.Response:
    payload: dict = {"name": "Product", "price": "9.99"}
    payload.update(extra)
    return await http.post("/api/test_products", json=payload)


async def test_create_link_by_id(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Books")

    response = await _create_product(auth_http, category=category["id"])

    assert response.status_code == 200
    assert response.json()["category"] == {"id": category["id"]}


async def test_create_link_by_object_id(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Music")

    response = await _create_product(auth_http, category={"id": category["id"]})

    assert response.status_code == 200
    assert response.json()["category"] == {"id": category["id"]}


async def test_create_link_and_update_related_record(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Old name")

    response = await _create_product(auth_http, category={"id": category["id"], "name": "New name"})

    assert response.status_code == 200
    assert response.json()["category"] == {"id": category["id"]}

    refreshed = (await auth_http.get(f"/api/test_categories/{category['id']}")).json()
    assert refreshed["name"] == "New name"


async def test_create_unlink_with_null(auth_http: httpx.AsyncClient) -> None:
    response = await _create_product(auth_http, category=None)

    assert response.status_code == 200
    assert response.json()["category"] is None


async def test_create_operation_link(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Games")

    response = await _create_product(auth_http, category=["link", category["id"]])

    assert response.status_code == 200
    assert response.json()["category"] == {"id": category["id"]}


async def test_create_operation_create_related_record(auth_http: httpx.AsyncClient) -> None:
    response = await _create_product(auth_http, category=["create", {"name": "Created inline"}])

    assert response.status_code == 200

    category_id = response.json()["category"]["id"]
    created = (await auth_http.get(f"/api/test_categories/{category_id}")).json()
    assert created["name"] == "Created inline"


async def test_patch_unlink_with_null(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Temp")
    product = (await _create_product(auth_http, category=category["id"])).json()

    response = await auth_http.patch(f"/api/test_products/{product['id']}", json={"category": None})

    assert response.status_code == 200
    assert response.json()["category"] is None


async def test_patch_operation_update_related_record(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Before")
    product = (await _create_product(auth_http)).json()

    response = await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"category": ["update", {"id": category["id"], "name": "After"}]},
    )

    assert response.status_code == 200
    assert response.json()["category"] == {"id": category["id"]}

    refreshed = (await auth_http.get(f"/api/test_categories/{category['id']}")).json()
    assert refreshed["name"] == "After"


async def test_patch_operation_unlink(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Linked")
    product = (await _create_product(auth_http, category=category["id"])).json()

    response = await auth_http.patch(f"/api/test_products/{product['id']}", json={"category": ["unlink"]})

    assert response.status_code == 200
    assert response.json()["category"] is None


async def test_operation_delete_removes_record_and_link(auth_http: httpx.AsyncClient) -> None:
    category = await _make_category(auth_http, "Doomed")
    product = (await _create_product(auth_http, category=category["id"])).json()

    response = await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"category": ["delete", category["id"]]},
    )

    assert response.status_code == 200
    assert response.json()["category"] is None

    assert (await auth_http.get(f"/api/test_categories/{category['id']}")).status_code == 404


async def test_link_missing_record_returns_400(auth_http: httpx.AsyncClient) -> None:
    response = await _create_product(auth_http, category=999999)

    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


async def test_required_foreign_key_cannot_be_unlinked(setup_openapi_app: FastEdgy) -> None:
    with pytest.raises(RelationOperationError, match="required"):
        await process_foreign_key_operation(Category, None, nullable=False, field_name="category")

    with pytest.raises(RelationOperationError, match="required"):
        await process_foreign_key_operation(Category, ["unlink"], nullable=False, field_name="category")
