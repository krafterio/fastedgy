# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What a view transformer costs the read it enriches.

A read that only reads is answered by its rows, without a model per row. A hook
receiving an item stands in the way, since nothing can know what it reaches
for: it gets its models, as it always did. Said with ``@view_transformer_reads``,
it is handed a view of its own row instead, and the read keeps its speed.
"""

from typing import Any

import httpx
import pytest

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import (
    GetViewTransformer,
    view_transformer_reads,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.test.models.category import Category
from fastedgy.test.models.product import Product

from .helpers import make_category, make_product


class _DeclaringTransformer(GetViewTransformer[Category]):
    """Says what it reads, and is served from the row."""

    seen: list[str] = []

    @view_transformer_reads("id", "name")
    async def get_view(
        self,
        request: Request,
        item: Category,
        item_dump: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        type(self).seen.append(type(item).__name__)
        item_dump["shouted"] = item.name.upper()

        return item_dump


class _SilentTransformer(GetViewTransformer[Category]):
    """Says nothing, and gets the models as before."""

    seen: list[str] = []

    async def get_view(
        self,
        request: Request,
        item: Category,
        item_dump: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        type(self).seen.append(type(item).__name__)
        item_dump["shouted"] = item.name.upper()

        return item_dump


class _NestedTransformer(GetViewTransformer[Product]):
    """Reads through a relation the read itself never asked for."""

    seen: list[str] = []

    @view_transformer_reads("category.name")
    async def get_view(
        self,
        request: Request,
        item: Product,
        item_dump: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        type(self).seen.append(type(item).__name__)
        item_dump["shelf"] = getattr(item.category, "name", None)

        return item_dump


def _register(transformer_cls: type[GetViewTransformer[Any]], model_cls: type = Category) -> None:
    transformer_cls.seen = []  # type: ignore[attr-defined]
    get_service(ViewTransformerRegistry).register_transformer(transformer_cls, model_cls)


@pytest.fixture(autouse=True)
def _isolated_registry():
    yield

    for model_cls in (Category, Product):
        ViewTransformerRegistry._transformers.pop(model_cls, None)


async def test_a_declared_transformer_is_served_from_the_row(auth_http: httpx.AsyncClient) -> None:
    _register(_DeclaringTransformer)
    await auth_http.post("/api/test_categories", json={"name": "Books"})

    payload = (await auth_http.get("/api/test_categories", headers={"X-Fields": "id"})).json()
    item = payload["items"][0]

    # The create above handed it a model; the read hands it a view of the row.
    assert _DeclaringTransformer.seen[-1] == "_RowValues"
    assert item["shouted"] == "BOOKS"
    # `name` was read for the hook alone: the answer carries what was asked.
    assert set(item) == {"id", "shouted"}


async def test_a_silent_transformer_keeps_its_models(auth_http: httpx.AsyncClient) -> None:
    _register(_SilentTransformer)
    await auth_http.post("/api/test_categories", json={"name": "Books"})

    payload = (await auth_http.get("/api/test_categories", headers={"X-Fields": "id"})).json()
    item = payload["items"][0]

    assert _SilentTransformer.seen[-1] == "Category"
    assert item["shouted"] == "BOOKS"
    assert set(item) == {"id", "shouted"}


async def test_a_declared_transformer_is_served_from_the_row_of_a_get(auth_http: httpx.AsyncClient) -> None:
    _register(_DeclaringTransformer)
    created = (await auth_http.post("/api/test_categories", json={"name": "Books"})).json()

    payload = (await auth_http.get(f"/api/test_categories/{created['id']}", headers={"X-Fields": "id"})).json()

    assert _DeclaringTransformer.seen[-1] == "_RowValues"
    assert payload["shouted"] == "BOOKS"
    assert set(payload) == {"id", "shouted"}


async def test_a_declared_read_reaches_through_a_relation(auth_http: httpx.AsyncClient) -> None:
    _register(_NestedTransformer, Product)
    category = await make_category(auth_http, "Tools")
    await make_product(auth_http, name="Laptop", category=category["id"])

    payload = (await auth_http.get("/api/test_products", headers={"X-Fields": "id,name"})).json()
    item = payload["items"][0]

    # The read named neither the relation nor its column: the declaration
    # joined it, and the answer still carries only what was asked.
    assert _NestedTransformer.seen[-1] == "_RowValues"
    assert item["shelf"] == "Tools"
    assert set(item) == {"id", "name", "shelf"}


async def test_a_declared_read_of_an_empty_relation_reads_as_none(auth_http: httpx.AsyncClient) -> None:
    _register(_NestedTransformer, Product)
    await make_product(auth_http, name="Laptop")

    payload = (await auth_http.get("/api/test_products", headers={"X-Fields": "id,name"})).json()

    # A model answers None for a relation nothing points at, and so does a row.
    assert payload["items"][0]["shelf"] is None
