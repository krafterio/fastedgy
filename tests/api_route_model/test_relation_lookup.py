# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from .helpers import get_product, make_product, make_tag, tag_ids


async def test_a_many_to_many_links_its_records_by_lookup(auth_http: httpx.AsyncClient) -> None:
    red = await make_tag(auth_http, "Red")
    blue = await make_tag(auth_http, "Blue")

    product = await make_product(auth_http, tags=["Red", blue["id"]])

    assert tag_ids(await get_product(auth_http, product["id"])) == {red["id"], blue["id"]}


async def test_the_operations_of_a_many_to_many_name_their_records_by_lookup(auth_http: httpx.AsyncClient) -> None:
    red = await make_tag(auth_http, "Red")
    blue = await make_tag(auth_http, "Blue")
    green = await make_tag(auth_http, "Green")
    product = await make_product(auth_http, tags=["Red", "Blue"])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["link", "Green"], ["unlink", "Red"]]})
    assert tag_ids(await get_product(auth_http, product["id"])) == {blue["id"], green["id"]}

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["set", ["Red", green["id"]]]]})
    assert tag_ids(await get_product(auth_http, product["id"])) == {red["id"], green["id"]}


async def test_a_reverse_one_to_many_links_its_records_by_the_related_lookup(auth_http: httpx.AsyncClient) -> None:
    phone = await make_product(auth_http, name="Pixel")

    response = await auth_http.post("/api/test_categories", json={"name": "Phones", "products": ["Pixel"]})

    assert response.status_code == 200, response.text
    assert (await get_product(auth_http, phone["id"]))["category"] == {"id": response.json()["id"], "name": "Phones"}


async def test_a_relation_lookup_that_matches_nothing_is_refused(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post("/api/test_products", json={"name": "Desk", "price": "1.00", "tags": ["Missing"]})

    assert response.status_code == 400
