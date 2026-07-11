# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

import httpx
import pytest
from sqlalchemy.exc import DBAPIError

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
