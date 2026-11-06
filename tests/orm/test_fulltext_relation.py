# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A fulltext search reaching the model it searches through a relation path."""

import json
from decimal import Decimal

import httpx

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import R, filter_query
from fastedgy.test.factories import authenticate, create_user
from fastedgy.test.models.category import Category
from fastedgy.test.models.comment import Comment
from fastedgy.test.models.product import Product


async def _commented() -> None:
    widget = Product(name="Widget", price=Decimal("9.99"))
    gadget = Product(name="Gadget", price=Decimal("9.99"))
    await widget.save()
    await gadget.save()
    await Comment(content="nice", product=widget).save()
    await Comment(content="meh", product=gadget).save()


async def test_a_search_reaches_the_model_it_searches_through_a_relation(setup_db: FastEdgy) -> None:
    await _commented()

    for operator in ("search", "search_fuzzy"):
        rows = await filter_query(Comment.query, R("product.search_value", operator, "widget")).all()

        assert [row.content for row in rows] == ["nice"], operator


async def test_a_search_through_a_relation_holds_with_an_ordering_on_it(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient
) -> None:
    await _commented()
    client = authenticate(setup_http, await create_user(email="me@example.io"))

    response = await client.get(
        "/api/test_comments",
        params={"order_by": "product.name:asc"},
        headers={"X-Filter": json.dumps(["product.search_value", "search_fuzzy", "widg"]), "X-Fields": "content"},
    )

    assert response.status_code == 200, response.text
    assert [item["content"] for item in response.json()["items"]] == ["nice"]


async def test_a_search_inside_an_any_block(setup_db: FastEdgy) -> None:
    books = Category(name="Books")
    tools = Category(name="Tools")
    await books.save()
    await tools.save()
    await Product(name="Widget", price=Decimal("1.00"), category=tools).save()
    await Product(name="Novel", price=Decimal("1.00"), category=books).save()

    rows = await filter_query(Category.query, R("products", "any", R("search_value", "search", "widget"))).all()

    assert [row.name for row in rows] == ["Tools"]


async def test_a_fuzzy_search_corrects_a_word_from_the_rows_the_request_reads(setup_db: FastEdgy) -> None:
    from fastedgy import context
    from fastedgy.test.factories import create_workspace, use_request
    from fastedgy.test.models.global_filter import GfDraft

    acme = await create_workspace(slug="acme")
    other = await create_workspace(slug="other")
    ada = await create_user(email="ada@example.io")
    bob = await create_user(email="bob@example.io")
    await GfDraft(body="widget", author=ada, workspace=acme).save()
    await GfDraft(body="widgte", author=bob, workspace=acme).save()
    await GfDraft(body="widgte", author=ada, workspace=other).save()

    with use_request(user=ada):
        context.set_workspace(acme)
        rows = await filter_query(GfDraft.query, R("search_value", "search_fuzzy", "widgte")).all()

    assert [row.body for row in rows] == ["widget"]


async def test_a_fuzzy_search_corrects_a_bounded_number_of_words(setup_db: FastEdgy) -> None:
    await _commented()

    rows = await filter_query(Product.query, R("search_value", "search_fuzzy", "widgte " + "zz " * 40)).all()

    assert [row.name for row in rows] == ["Widget"]
