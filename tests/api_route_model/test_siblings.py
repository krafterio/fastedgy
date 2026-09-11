# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

import httpx

from .helpers import make_category, make_product


async def _siblings(client: httpx.AsyncClient, item_id: int, order_by: str | None = None, rule=None) -> dict:
    response = await client.get(
        f"/api/test_products/{item_id}/siblings",
        params={"order_by": order_by} if order_by else {},
        headers={"X-Filter": json.dumps(rule)} if rule is not None else {},
    )

    assert response.status_code == 200, response.text

    return response.json()


async def test_siblings_follow_the_order_of_a_text_field(auth_http: httpx.AsyncClient) -> None:
    bravo = await make_product(auth_http, name="Bravo")
    alpha = await make_product(auth_http, name="Alpha")
    charlie = await make_product(auth_http, name="Charlie")

    assert await _siblings(auth_http, bravo["id"], "name") == {"previous": alpha["id"], "next": charlie["id"]}
    assert await _siblings(auth_http, alpha["id"], "name") == {"previous": None, "next": bravo["id"]}
    assert await _siblings(auth_http, alpha["id"], "name:desc") == {"previous": bravo["id"], "next": None}


async def test_siblings_break_ties_on_the_id(auth_http: httpx.AsyncClient) -> None:
    first = await make_product(auth_http, name="Same")
    second = await make_product(auth_http, name="Same")
    third = await make_product(auth_http, name="Same")

    assert await _siblings(auth_http, second["id"], "name") == {"previous": first["id"], "next": third["id"]}


async def test_siblings_stay_within_the_filter(auth_http: httpx.AsyncClient) -> None:
    books = await make_category(auth_http, "Books")
    games = await make_category(auth_http, "Games")

    alpha = await make_product(auth_http, name="Alpha", category=books["id"])
    await make_product(auth_http, name="Bravo", category=games["id"])
    charlie = await make_product(auth_http, name="Charlie", category=books["id"])

    rule = ["category", "=", books["id"]]

    assert await _siblings(auth_http, alpha["id"], "name", rule) == {"previous": None, "next": charlie["id"]}


async def test_siblings_of_a_record_outside_the_filter_are_empty(auth_http: httpx.AsyncClient) -> None:
    books = await make_category(auth_http, "Books")

    await make_product(auth_http, name="Alpha", category=books["id"])
    stray = await make_product(auth_http, name="Bravo")

    rule = ["category", "=", books["id"]]

    assert await _siblings(auth_http, stray["id"], "name", rule) == {"previous": None, "next": None}


async def test_siblings_follow_a_relation_path(auth_http: httpx.AsyncClient) -> None:
    zeta = await make_category(auth_http, "Zeta")
    beta = await make_category(auth_http, "Beta")

    last = await make_product(auth_http, name="Alpha", category=zeta["id"])
    first = await make_product(auth_http, name="Bravo", category=beta["id"])

    assert await _siblings(auth_http, first["id"], "category.name") == {"previous": None, "next": last["id"]}


async def test_siblings_reject_an_invalid_filter(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)

    response = await auth_http.get(
        f"/api/test_products/{product['id']}/siblings",
        headers={"X-Filter": json.dumps(["unknown", "=", 1])},
    )

    assert response.status_code == 422


async def test_siblings_are_opt_in(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http)

    response = await auth_http.get(f"/api/test_categories/{category['id']}/siblings")

    assert response.status_code in (404, 405)
