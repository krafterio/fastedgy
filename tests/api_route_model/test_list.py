# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

import httpx

from .helpers import make_category, make_product, make_tag


async def _seed_categories(client: httpx.AsyncClient, names: list[str]) -> list[dict]:
    created = []
    for name in names:
        created.append((await client.post("/api/test_categories", json={"name": name})).json())
    return created


async def test_list_metadata_shape(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["A", "B", "C"])

    payload = (await auth_http.get("/api/test_categories")).json()

    assert payload["total"] == 3
    assert len(payload["items"]) == 3
    assert set(payload) >= {"items", "total", "limit", "offset", "total_pages"}


async def test_list_pagination_limit_and_offset(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["A", "B", "C", "D", "E"])

    first = (await auth_http.get("/api/test_categories?limit=2&offset=0")).json()
    second = (await auth_http.get("/api/test_categories?limit=2&offset=2")).json()

    assert first["total"] == 5
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert first["total_pages"] == 3

    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}

    assert first_ids.isdisjoint(second_ids)


async def test_list_limit_zero_returns_count_only(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["A", "B", "C"])

    payload = (await auth_http.get("/api/test_categories?limit=0")).json()

    assert payload["total"] == 3
    assert payload["items"] == []


async def test_list_order_by_field(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["Charlie", "Alpha", "Bravo"])

    payload = (await auth_http.get("/api/test_categories?order_by=name")).json()

    names = [item["name"] for item in payload["items"]]

    assert names == ["Alpha", "Bravo", "Charlie"]


async def test_list_order_by_descending(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["Alpha", "Bravo", "Charlie"])

    payload = (await auth_http.get("/api/test_categories?order_by=name:desc")).json()

    names = [item["name"] for item in payload["items"]]

    assert names == ["Charlie", "Bravo", "Alpha"]


async def test_field_selection_limits_returned_fields(auth_http: httpx.AsyncClient) -> None:
    await auth_http.post("/api/test_categories", json={"name": "Books", "description": "hidden"})

    payload = (await auth_http.get("/api/test_categories", headers={"X-Fields": "name"})).json()

    item = payload["items"][0]

    assert item["name"] == "Books"
    assert "description" not in item


async def test_filter_by_field_equality(auth_http: httpx.AsyncClient) -> None:
    await _seed_categories(auth_http, ["Books", "Movies", "Music"])

    payload = (
        await auth_http.get(
            "/api/test_categories",
            headers={"X-Filter": json.dumps(["name", "=", "Movies"])},
        )
    ).json()

    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Movies"


async def test_filter_by_related_field(auth_http: httpx.AsyncClient) -> None:
    electronics = await make_category(auth_http, "Electronics")
    books = await make_category(auth_http, "Books")
    await make_product(auth_http, name="Phone", category=electronics["id"])
    await make_product(auth_http, name="Novel", category=books["id"])

    payload = (
        await auth_http.get(
            "/api/test_products",
            headers={"X-Filter": json.dumps(["category.name", "=", "Books"])},
        )
    ).json()

    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Novel"


async def test_list_order_by_reverse_relation_keeps_one_row_per_record(auth_http: httpx.AsyncClient) -> None:
    # Ordering on a path through an inverse relation joins the many side, and one
    # parent row per child multiplies the result set: the page comes back short,
    # `total` counts join rows and a record shows up again on the next page.
    big = await make_category(auth_http, "Big")
    small = await make_category(auth_http, "Small")
    await make_category(auth_http, "Empty")

    for name, price in (("P1", "10.00"), ("P2", "20.00"), ("P3", "30.00")):
        await make_product(auth_http, name=name, price=price, category=big["id"])
    await make_product(auth_http, name="P4", price="40.00", category=small["id"])

    payload = (await auth_http.get("/api/test_categories?order_by=products.price:asc&limit=10")).json()
    ids = [item["id"] for item in payload["items"]]

    assert payload["total"] == 3
    assert len(ids) == 3
    assert len(set(ids)) == len(ids)

    first = (await auth_http.get("/api/test_categories?order_by=products.price:asc&limit=2&offset=0")).json()
    second = (await auth_http.get("/api/test_categories?order_by=products.price:asc&limit=2&offset=2")).json()
    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}

    assert len(first["items"]) == 2
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == set(ids)


async def test_list_order_by_reverse_relation_sorts_on_the_extreme_value(auth_http: httpx.AsyncClient) -> None:
    # Ascending ranks a record by its smallest related value, descending by its
    # largest, which is the order the join yielded before it was aggregated.
    cheap = await make_category(auth_http, "Cheap")
    pricey = await make_category(auth_http, "Pricey")

    await make_product(auth_http, name="C1", price="5.00", category=cheap["id"])
    await make_product(auth_http, name="C2", price="500.00", category=cheap["id"])
    await make_product(auth_http, name="P1", price="100.00", category=pricey["id"])
    await make_product(auth_http, name="P2", price="200.00", category=pricey["id"])

    ascending = (await auth_http.get("/api/test_categories?order_by=products.price:asc")).json()
    descending = (await auth_http.get("/api/test_categories?order_by=products.price:desc")).json()

    assert [item["name"] for item in ascending["items"]] == ["Cheap", "Pricey"]
    assert [item["name"] for item in descending["items"]] == ["Cheap", "Pricey"]
    assert ascending["total"] == 2


async def test_list_order_by_many_to_many_keeps_one_row_per_record(auth_http: httpx.AsyncClient) -> None:
    # A many-to-many fans out the same way a reverse one-to-many does.
    sale = await make_tag(auth_http, "sale")
    new = await make_tag(auth_http, "new")

    await make_product(auth_http, name="Tagged", tags=[sale["id"], new["id"]])
    await make_product(auth_http, name="Plain")

    payload = (await auth_http.get("/api/test_products?order_by=tags.name:asc")).json()
    ids = [item["id"] for item in payload["items"]]

    assert payload["total"] == 2
    assert len(ids) == len(set(ids)) == 2


async def test_list_filter_and_order_on_the_same_reverse_relation(auth_http: httpx.AsyncClient) -> None:
    # A single rule over the relation compiles to EXISTS, so nothing repeats the
    # record and the aggregate is free to sort the page.
    big = await make_category(auth_http, "Big")
    small = await make_category(auth_http, "Small")

    await make_product(auth_http, name="P1", price="20.00", category=big["id"])
    await make_product(auth_http, name="P2", price="30.00", category=big["id"])
    await make_product(auth_http, name="P3", price="40.00", category=small["id"])

    payload = (
        await auth_http.get(
            "/api/test_categories?order_by=products.price:asc",
            headers={"X-Filter": json.dumps(["products.price", ">", "15"])},
        )
    ).json()
    ids = [item["id"] for item in payload["items"]]

    assert payload["total"] == 2
    assert len(ids) == len(set(ids)) == 2
    assert [item["name"] for item in payload["items"]] == ["Big", "Small"]


async def test_list_filter_twice_on_one_relation_keeps_the_shared_join(auth_http: httpx.AsyncClient) -> None:
    # Two rules over the same relation mean one related row has to satisfy both,
    # which only a shared join expresses: it keeps its DISTINCT ON, and the
    # ordering stays on the join rather than becoming an aggregate.
    tagged = await make_product(auth_http, name="Tagged", price="10.00")
    urgent = await make_tag(auth_http, "urgent")
    unfiled = await make_tag(auth_http, "unfiled")
    await auth_http.patch(f"/api/test_products/{tagged['id']}", json={"tags": [urgent["id"], unfiled["id"]]})
    await make_product(auth_http, name="Plain", price="20.00")

    response = await auth_http.get(
        "/api/test_products?order_by=tags.name:asc",
        headers={"X-Filter": json.dumps(["&", [["tags.name", "icontains", "u"], ["tags.name", "!=", "urgent"]]])},
    )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Tagged"]
