# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What a read answers never depends on how it was answered.

A read that only reads is served from its rows; anything else builds its models.
Both must say exactly the same thing, whatever the column holds: a moment, an
amount, a uuid, a choice, or a relation.
"""

from typing import Any
from uuid import uuid4

import httpx
import pytest

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.row_read import plan_row_read
from fastedgy.api_route_model.view_transformer import GetViewTransformer
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.models.extra_field_model import WorkspaceExtraFieldModel
from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType
from fastedgy.test.models.product import Product
from fastedgy.test.models.workspace_extra_field import WorkspaceExtraField

from .helpers import make_category, make_product, make_tag


class _SilentTransformer(GetViewTransformer[Any]):
    """Says nothing of what it reads, which sends the read to the models."""

    async def get_view(
        self,
        request: Request,
        item: Any,
        item_dump: dict[str, Any],
        ctx: dict[str, Any],
    ) -> dict[str, Any]:
        return item_dump


@pytest.fixture(autouse=True)
def _isolated_registry():
    yield

    for model_cls in (Product, WorkspaceExtraField):
        ViewTransformerRegistry._transformers.pop(model_cls, None)


async def _both_ways(client: httpx.AsyncClient, path: str, fields: str, model_cls: type) -> tuple[Any, Any]:
    # Both reads would otherwise be the same one, and the test would compare
    # the model path to itself.
    assert plan_row_read(model_cls, fields) is not None

    from_rows = (await client.get(path, headers={"X-Fields": fields})).json()

    get_service(ViewTransformerRegistry).register_transformer(_SilentTransformer, model_cls)

    from_models = (await client.get(path, headers={"X-Fields": fields})).json()

    return from_rows, from_models


async def test_a_list_answers_the_same_from_its_rows(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Tools")
    tags = [await make_tag(auth_http, name) for name in ("beta", "alpha")]
    await make_product(
        auth_http,
        name="Laptop",
        price="999.90",
        description="<p>Hello</p>",
        quantity=3,
        rating=4.5,
        released_on="2026-01-31",
        published_at="2026-01-31T08:30:00Z",
        reference=str(uuid4()),
        details={"color": "black"},
        category=category["id"],
        tags=[tag["id"] for tag in tags],
    )
    fields = (
        "name,description,price,is_active,quantity,rating,released_on,published_at,"
        "reference,details,created_at,category.name,tags.name"
    )

    from_rows, from_models = await _both_ways(auth_http, "/api/test_products", fields, Product)

    assert from_rows == from_models
    assert from_rows["items"][0]["price"] == from_models["items"][0]["price"]


async def test_a_choice_answers_the_same_from_its_row(auth_http: httpx.AsyncClient) -> None:
    await auth_http.post(
        "/api/workspace_extra_fields",
        json={
            "label": "Priority",
            "name": "priority",
            "model": WorkspaceExtraFieldModel.product.name,
            "field_type": WorkspaceExtraFieldType.integer.name,
        },
    )
    fields = "label,name,model,field_type,required"

    from_rows, from_models = await _both_ways(auth_http, "/api/workspace_extra_fields", fields, WorkspaceExtraField)

    assert from_rows["items"][0]["field_type"] == "integer"
    assert from_rows == from_models


async def test_a_record_answers_the_same_from_its_row(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Tools")
    created = await make_product(auth_http, name="Laptop", category=category["id"], released_on="2026-01-31")
    fields = "name,price,released_on,updated_at,category.name"

    from_rows, from_models = await _both_ways(auth_http, f"/api/test_products/{created['id']}", fields, Product)

    assert from_rows == from_models
