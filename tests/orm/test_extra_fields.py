# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

from decimal import Decimal

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.orm.field_selector import filter_selected_fields
from fastedgy.orm.filter.builder import filter_query
from fastedgy.orm.order_by import inject_order_by, parse_order_by
from fastedgy.test.factories import use_request
from fastedgy.test.models.product import Product
from fastedgy.test.models.workspace_extra_field import (
    WorkspaceExtraField,
    WorkspaceExtraFieldModel,
)
from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType


def _extra_field(name: str, field_type: WorkspaceExtraFieldType) -> WorkspaceExtraField:
    return WorkspaceExtraField(
        label=name.title(),
        name=name,
        field_type=field_type,
        model=WorkspaceExtraFieldModel.product,
    )


def _declare_extra_fields() -> None:
    context.set_workspace_extra_fields(
        [
            _extra_field("priority", WorkspaceExtraFieldType.integer),
            _extra_field("owner", WorkspaceExtraFieldType.char),
        ]
    )


async def _create_products() -> None:
    await Product.query.create(name="Alpha", price=Decimal("1.00"), extra={"priority": 2, "owner": "ada"})
    await Product.query.create(name="Beta", price=Decimal("2.00"), extra={"priority": 1, "owner": "grace"})
    await Product.query.create(name="Gamma", price=Decimal("3.00"), extra=None)


async def test_context_keeps_every_extra_field_of_a_model(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()

        assert sorted(context.get_map_workspace_extra_fields("product")) == ["owner", "priority"]


async def test_order_by_accepts_a_declared_extra_field(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()

        assert parse_order_by(Product, "extra_priority:desc") == [("extra_priority", "desc")]


async def test_order_by_drops_an_undeclared_extra_field(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()

        assert parse_order_by(Product, "extra_unknown") == []


async def test_order_by_sorts_on_the_extra_field_value(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        query = inject_order_by(Product.query.get_queryset(), "extra_priority")
        names = [product.name for product in await query.all()]

        assert names[:2] == ["Beta", "Alpha"]


async def test_filter_matches_on_the_extra_field_value(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        query = filter_query(Product.query.get_queryset(), json.dumps(["extra_owner", "=", "ada"]))

        assert [product.name for product in await query.all()] == ["Alpha"]


async def test_selection_returns_the_extra_field_flattened(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        product = await Product.query.filter(name="Alpha").get()
        dump = await filter_selected_fields(product, "id,name,extra_priority")

        assert dump["extra_priority"] == 2
        assert "extra" not in dump


async def test_selection_returns_null_for_a_record_without_extra(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        product = await Product.query.filter(name="Gamma").get()
        dump = await filter_selected_fields(product, "id,extra_priority")

        assert dump["extra_priority"] is None
