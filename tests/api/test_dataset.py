# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError

from fastedgy.api_route_model.registry import (
    CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelRegistry,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import PreSaveTransformer
from fastedgy.dependencies import get_service, register_service
from fastedgy.http import Request
from fastedgy.sudo import SudoChecker
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product


async def test_metadatas_describe_registered_models(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/dataset/metadatas")

    assert response.status_code == 200

    data = response.json()

    assert "product" in data

    product = data["product"]

    assert product["api_name"] == "test_products"
    assert product["searchable"] is True
    assert product["search_field"] == "search_value"
    assert "name" in product["fields"]


async def test_metadatas_require_authentication(setup_http: httpx.AsyncClient) -> None:
    assert (await setup_http.get("/api/dataset/metadatas")).status_code == 401


async def test_resequence_unknown_model_is_rejected(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.put(
        "/api/dataset/resequence",
        json={"model_name": "does_not_exist", "sequence_field": "sequence", "ids": [1]},
    )

    assert response.status_code == 400


async def _make_products(auth_http: httpx.AsyncClient, *names: str) -> list[int]:
    ids = []
    for name in names:
        response = await auth_http.post("/api/test_products", json={"name": name, "price": "1.00"})
        ids.append(response.json()["id"])
    return ids


async def _resequence_products(auth_http: httpx.AsyncClient, ids: list[int]) -> httpx.Response:
    return await auth_http.put(
        "/api/dataset/resequence",
        json={"model_name": "product", "sequence_field": "quantity", "ids": ids},
    )


async def test_resequence_applies_sequence_in_ids_order(auth_http: httpx.AsyncClient) -> None:
    id_a, id_b = await _make_products(auth_http, "A", "B")

    response = await _resequence_products(auth_http, [id_b, id_a])

    assert response.status_code == 200
    assert {r["id"]: r["quantity"] for r in response.json()["records"]} == {id_b: 0, id_a: 1}

    products = await Product.query.filter(Product.columns.id.in_([id_a, id_b])).all()

    assert {p.id: p.quantity for p in products} == {id_b: 0, id_a: 1}


async def test_resequence_retries_on_serialization_conflict(
    auth_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    id_a, id_b = await _make_products(auth_http, "A", "B")

    class _SerializationOrig(Exception):
        sqlstate = "40001"

    real_save = Product.save
    calls = {"n": 0}

    async def flaky_save(self: Product, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise DBAPIError("UPDATE", None, _SerializationOrig())
        return await real_save(self, *args, **kwargs)

    monkeypatch.setattr(Product, "save", flaky_save)

    response = await _resequence_products(auth_http, [id_b, id_a])

    assert response.status_code == 200
    assert calls["n"] == 3

    products = await Product.query.filter(Product.columns.id.in_([id_a, id_b])).all()

    assert {p.id: p.quantity for p in products} == {id_b: 0, id_a: 1}


class _RefusingQuantity(PreSaveTransformer[Product]):
    async def pre_save(
        self, request: Request, item: Product, item_data: Any, ctx: dict[str, Any], created: bool
    ) -> None:
        if "quantity" in item_data.model_fields_set:
            raise HTTPException(status_code=403, detail="quantity is not yours")


class _AlwaysSudo(SudoChecker):
    async def is_sudo(self) -> bool:
        return True


@pytest.fixture
def refusing_quantity() -> Iterator[None]:
    ViewTransformerRegistry._transformers.pop(Product, None)
    get_service(ViewTransformerRegistry).register_transformer(_RefusingQuantity, Product)
    yield
    ViewTransformerRegistry._transformers.pop(Product, None)


@pytest.fixture
def console_only_category() -> Iterator[None]:
    api_registry = get_service(RouteModelRegistry)
    console_registry = get_service(CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN)
    console_registry._models[Category] = api_registry._models.pop(Category)
    yield
    api_registry._models[Category] = console_registry._models.pop(Category)


@pytest.fixture
def sudo() -> Iterator[None]:
    original = get_service(SudoChecker)
    register_service(_AlwaysSudo(), SudoChecker, force=True)
    yield
    register_service(original, SudoChecker, force=True)


async def test_resequence_refuses_a_field_the_patch_route_does_not_write(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="A", price="1.00", secret_code="kept")

    response = await auth_http.put(
        "/api/dataset/resequence",
        json={"model_name": "product", "ids": [product.id], "group_field": "secret_code", "group_value": "stolen"},
    )

    assert response.status_code == 400
    assert (await Product.query.get(id=product.id)).secret_code == "kept"


async def test_resequence_refuses_a_read_only_field(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.ticket import Ticket

    ticket = await Ticket.query.create(subject="Help")

    response = await auth_http.put(
        "/api/dataset/resequence",
        json={"model_name": "ticket", "ids": [ticket.id], "group_field": "reference", "group_value": "FORGED"},
    )

    assert response.status_code == 400
    assert (await Ticket.query.get(id=ticket.id)).reference != "FORGED"


async def test_resequence_refuses_a_model_without_patch_route(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.comment import Comment

    comment = await Comment.query.create(content="first")

    response = await auth_http.put(
        "/api/dataset/resequence",
        json={"model_name": "comment", "ids": [comment.id], "group_field": "content", "group_value": "rewritten"},
    )

    assert response.status_code == 405
    assert (await Comment.query.get(id=comment.id)).content == "first"


async def test_resequence_runs_the_model_transformers(auth_http: httpx.AsyncClient, refusing_quantity: None) -> None:
    id_a, id_b = await _make_products(auth_http, "A", "B")

    response = await _resequence_products(auth_http, [id_b, id_a])

    assert response.status_code == 403

    products = await Product.query.filter(Product.columns.id.in_([id_a, id_b])).all()

    assert {p.quantity for p in products} == {0}


async def test_resequence_leaves_a_console_model_to_sudo(
    auth_http: httpx.AsyncClient, console_only_category: None
) -> None:
    category = await Category.query.create(name="Before")
    body = {"model_name": "category", "ids": [category.id], "group_field": "name", "group_value": "After"}

    assert (await auth_http.put("/api/dataset/resequence", json=body)).status_code == 403
    assert (await Category.query.get(id=category.id)).name == "Before"


async def test_resequence_writes_a_console_model_for_sudo(
    auth_http: httpx.AsyncClient, console_only_category: None, sudo: None
) -> None:
    category = await Category.query.create(name="Before")
    body = {"model_name": "category", "ids": [category.id], "group_field": "name", "group_value": "After"}

    assert (await auth_http.put("/api/dataset/resequence", json=body)).status_code == 200
    assert (await Category.query.get(id=category.id)).name == "After"
