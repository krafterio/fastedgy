# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from .helpers import get_product, make_category, make_product, make_tag, tag_ids


async def test_patch_updates_only_provided_fields(auth_http: httpx.AsyncClient) -> None:
    created = (await auth_http.post("/api/test_categories", json={"name": "Old", "description": "keep me"})).json()

    response = await auth_http.patch(f"/api/test_categories/{created['id']}", json={"name": "New"})

    assert response.status_code == 200

    item = response.json()

    assert item["name"] == "New"
    assert item["description"] == "keep me"


async def test_patch_unknown_item_returns_404(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.patch("/api/test_categories/999999", json={"name": "Nope"})

    assert response.status_code == 404


# --- ForeignKey -------------------------------------------------------------


async def test_patch_foreign_key(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Toys")
    product = await make_product(auth_http)

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"category": category["id"]})

    fetched = await get_product(auth_http, product["id"])

    assert fetched["category"]["id"] == category["id"]


# --- ManyToMany: simple mode ------------------------------------------------


async def test_simple_mode_replaces_all_relations(auth_http: httpx.AsyncClient) -> None:
    t1 = await make_tag(auth_http, "a")
    t2 = await make_tag(auth_http, "b")
    t3 = await make_tag(auth_http, "c")
    product = await make_product(auth_http, tags=[t1["id"], t2["id"]])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [t3["id"]]})

    assert tag_ids(await get_product(auth_http, product["id"])) == {t3["id"]}


# --- ManyToMany: advanced mode operations -----------------------------------


async def test_advanced_link_and_unlink(auth_http: httpx.AsyncClient) -> None:
    t1 = await make_tag(auth_http, "a")
    t2 = await make_tag(auth_http, "b")
    product = await make_product(auth_http, tags=[t1["id"]])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["link", t2["id"]]]})
    assert tag_ids(await get_product(auth_http, product["id"])) == {t1["id"], t2["id"]}

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["unlink", t1["id"]]]})
    assert tag_ids(await get_product(auth_http, product["id"])) == {t2["id"]}


async def test_advanced_set_and_clear(auth_http: httpx.AsyncClient) -> None:
    t1 = await make_tag(auth_http, "a")
    t2 = await make_tag(auth_http, "b")
    product = await make_product(auth_http, tags=[t1["id"]])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["set", [t1["id"], t2["id"]]]]})
    assert tag_ids(await get_product(auth_http, product["id"])) == {t1["id"], t2["id"]}

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["clear"]]})
    assert tag_ids(await get_product(auth_http, product["id"])) == set()


async def test_advanced_create_links_new_record(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)

    await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"tags": [["create", {"name": "Fresh"}]]},
    )

    fetched = await get_product(auth_http, product["id"])
    tags = fetched.get("tags") or []

    assert len(tags) == 1
    assert tags[0]["name"] == "Fresh"
    assert (await auth_http.get("/api/test_tags")).json()["total"] == 1


async def test_advanced_update_modifies_and_links(auth_http: httpx.AsyncClient) -> None:
    tag = await make_tag(auth_http, "Original")
    product = await make_product(auth_http)

    await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"tags": [["update", {"id": tag["id"], "name": "Updated"}]]},
    )

    fetched = await get_product(auth_http, product["id"])

    assert tag_ids(fetched) == {tag["id"]}
    assert (await auth_http.get(f"/api/test_tags/{tag['id']}")).json()["name"] == "Updated"


async def test_advanced_delete_removes_record(auth_http: httpx.AsyncClient) -> None:
    t1 = await make_tag(auth_http, "a")
    t2 = await make_tag(auth_http, "b")
    product = await make_product(auth_http, tags=[t1["id"], t2["id"]])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"tags": [["delete", t1["id"]]]})

    fetched = await get_product(auth_http, product["id"])

    assert tag_ids(fetched) == {t2["id"]}
    assert (await auth_http.get(f"/api/test_tags/{t1['id']}")).status_code == 404


async def test_advanced_operations_run_in_order(auth_http: httpx.AsyncClient) -> None:
    t1 = await make_tag(auth_http, "a")
    t2 = await make_tag(auth_http, "b")
    product = await make_product(auth_http, tags=[t1["id"]])

    await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"tags": [["clear"], ["link", t1["id"]], ["link", t2["id"]]]},
    )

    assert tag_ids(await get_product(auth_http, product["id"])) == {t1["id"], t2["id"]}


# --- Errors -----------------------------------------------------------------


async def test_link_unknown_record_is_rejected(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)

    response = await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"tags": [["link", 999999]]},
    )

    assert response.status_code == 400


async def test_invalid_operation_format_is_rejected(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http)

    response = await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"tags": [["link"]]},
    )

    assert response.status_code == 400
