# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from fastedgy.test.models.note import Note
from fastedgy.test.models.product import Product


async def _make_product(auth_http: httpx.AsyncClient, name: str = "Widget") -> dict:
    response = await auth_http.post("/api/test_products", json={"name": name, "price": "9.99"})
    assert response.status_code == 200, response.text
    return response.json()


async def test_create_with_reference_object(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http)

    response = await auth_http.post(
        "/api/test_notes",
        json={"content": "linked", "subject": {"model": "product", "id": product["id"]}},
    )
    assert response.status_code == 200, response.text

    note = await Note.query.get(id=response.json()["id"])
    assert note.subject_model == "product"
    assert note.subject_id == product["id"]


async def test_create_without_reference(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post("/api/test_notes", json={"content": "free"})
    assert response.status_code == 200, response.text

    note = await Note.query.get(id=response.json()["id"])
    assert note.subject_model is None
    assert note.subject_id is None


async def test_patch_reference_retargets_and_clears(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http)
    other = await _make_product(auth_http, "Other")

    created = await auth_http.post(
        "/api/test_notes",
        json={"content": "moved", "subject": {"model": "product", "id": product["id"]}},
    )
    note_id = created.json()["id"]

    retargeted = await auth_http.patch(
        f"/api/test_notes/{note_id}",
        json={"subject": {"model": "product", "id": other["id"]}},
    )
    assert retargeted.status_code == 200, retargeted.text
    note = await Note.query.get(id=note_id)
    assert note.subject_id == other["id"]

    cleared = await auth_http.patch(f"/api/test_notes/{note_id}", json={"subject": None})
    assert cleared.status_code == 200, cleared.text
    note = await Note.query.get(id=note_id)
    assert note.subject_model is None
    assert note.subject_id is None


async def test_reference_columns_are_hidden_from_the_api(auth_http: httpx.AsyncClient) -> None:
    import json

    product = await _make_product(auth_http)

    response = await auth_http.post(
        "/api/test_notes",
        json={"content": "flat", "subject_model": "product", "subject_id": product["id"]},
    )
    assert response.status_code == 200, response.text

    note = await Note.query.get(id=response.json()["id"])
    assert note.subject_model is None
    assert note.subject_id is None
    assert "subject_model" not in response.json()

    flat_filter = ["subject_model", "=", "product"]
    filtered = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(flat_filter)})
    assert filtered.status_code == 422, filtered.text


async def test_create_parent_with_inline_generic_children(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/test_products",
        json={
            "name": "With notes",
            "price": "9.99",
            "notes": [["create", {"content": "first"}], ["create", {"content": "second"}]],
        },
    )
    assert response.status_code == 200, response.text
    product_id = response.json()["id"]

    notes = await Note.query.filter(subject_model="product", subject_id=product_id).order_by("id").all()
    assert [note.content for note in notes] == ["first", "second"]


async def test_create_parent_with_plain_dict_children(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/test_products",
        json={"name": "Dict notes", "price": "9.99", "notes": [{"content": "inline"}]},
    )
    assert response.status_code == 200, response.text
    product_id = response.json()["id"]

    notes = await Note.query.filter(subject_model="product", subject_id=product_id).all()
    assert [note.content for note in notes] == ["inline"]


async def test_fields_selector_serializes_reference_target(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http, "Selected")

    created = await auth_http.post(
        "/api/test_notes",
        json={"content": "with subject", "subject": {"model": "product", "id": product["id"]}},
    )
    note_id = created.json()["id"]

    response = await auth_http.get(
        f"/api/test_notes/{note_id}",
        headers={"X-Fields": "content,subject.$model,subject.name"},
    )
    assert response.status_code == 200, response.text

    item = response.json()
    assert item["content"] == "with subject"
    assert "subject_model" not in item
    assert item["subject"]["$model"] == "product"
    assert item["subject"]["name"] == "Selected"
    assert item["subject"]["id"] == product["id"]


async def test_fields_selector_reference_null_when_unset(auth_http: httpx.AsyncClient) -> None:
    created = await auth_http.post("/api/test_notes", json={"content": "bare"})
    note_id = created.json()["id"]

    response = await auth_http.get(f"/api/test_notes/{note_id}", headers={"X-Fields": "content,subject.name"})
    assert response.status_code == 200, response.text
    assert response.json()["subject"] is None


async def test_fields_selector_list_batches_reference_loading(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http, "Batched")
    other = await _make_product(auth_http, "Other")

    for index in range(3):
        target = product if index % 2 == 0 else other
        await auth_http.post(
            "/api/test_notes",
            json={"content": f"n{index}", "subject": {"model": "product", "id": target["id"]}},
        )

    response = await auth_http.get("/api/test_notes", headers={"X-Fields": "content,subject.name"})
    assert response.status_code == 200, response.text

    items = response.json()["items"]
    by_content = {item["content"]: item["subject"]["name"] for item in items if item["content"].startswith("n")}
    assert by_content == {"n0": "Batched", "n1": "Other", "n2": "Batched"}


async def test_fields_selector_inverse_relation(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/test_products",
        json={"name": "Parent", "price": "9.99", "notes": [{"content": "child one"}, {"content": "child two"}]},
    )
    product_id = response.json()["id"]

    fetched = await auth_http.get(
        f"/api/test_products/{product_id}",
        headers={"X-Fields": "name,notes.content"},
    )
    assert fetched.status_code == 200, fetched.text

    item = fetched.json()
    assert item["name"] == "Parent"
    assert [note["content"] for note in item["notes"]] == ["child one", "child two"]


async def test_reference_with_unknown_model_is_rejected(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/test_notes",
        json={"content": "bad", "subject": {"model": "tag", "id": 1}},
    )
    assert response.status_code == 422, response.text


async def test_inverse_relation_exposed_on_every_target(auth_http: httpx.AsyncClient) -> None:
    import json

    category = await auth_http.post("/api/test_categories", json={"name": "Bikes"})
    category_id = category.json()["id"]

    response = await auth_http.patch(
        f"/api/test_categories/{category_id}",
        json={"notes": [{"content": "on category"}]},
    )
    assert response.status_code == 200, response.text

    fetched = await auth_http.get(f"/api/test_categories/{category_id}", headers={"X-Fields": "name,notes.content"})
    assert fetched.status_code == 200, fetched.text
    assert [note["content"] for note in fetched.json()["notes"]] == ["on category"]

    reference_filter = ["subject", "=", ["category", category_id]]
    filtered = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(reference_filter)})
    assert filtered.status_code == 200, filtered.text
    assert [item["content"] for item in filtered.json()["items"]] == ["on category"]


async def test_filter_by_reference_in_and_empty(auth_http: httpx.AsyncClient) -> None:
    import json

    products = []
    for name in ("A", "B", "C"):
        products.append(await _make_product(auth_http, name))

    for index, product in enumerate(products):
        await auth_http.post(
            "/api/test_notes",
            json={"content": f"ref-{index}", "subject": {"model": "product", "id": product["id"]}},
        )
    await auth_http.post("/api/test_notes", json={"content": "ref-free"})

    in_filter = ["subject", "in", [["product", products[0]["id"]], ["product", products[2]["id"]]]]
    response = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(in_filter)})
    assert response.status_code == 200, response.text
    assert sorted(item["content"] for item in response.json()["items"]) == ["ref-0", "ref-2"]

    pair_paths = [
        "&",
        [["subject.$model", "=", "product"], ["subject.id", "in", [products[0]["id"], products[2]["id"]]]],
    ]
    response = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(pair_paths)})
    assert response.status_code == 200, response.text
    assert sorted(item["content"] for item in response.json()["items"]) == ["ref-0", "ref-2"]

    empty_filter = ["subject", "is empty"]
    response = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(empty_filter)})
    assert response.status_code == 200, response.text
    assert [item["content"] for item in response.json()["items"]] == ["ref-free"]

    not_empty_filter = ["subject", "is not empty"]
    response = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(not_empty_filter)})
    assert response.status_code == 200, response.text
    assert sorted(item["content"] for item in response.json()["items"]) == ["ref-0", "ref-1", "ref-2"]


async def test_filter_by_reference_unknown_model_rejected(auth_http: httpx.AsyncClient) -> None:
    import json

    bad_filter = ["subject", "=", ["tag", 1]]
    response = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(bad_filter)})
    assert response.status_code == 422, response.text

    object_value = ["subject", "=", {"model": "product", "id": 1}]
    response = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(object_value)})
    assert response.status_code == 422, response.text


async def test_patch_parent_set_and_clear_generic_children(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Holder", price="9.99")
    kept = await Note.query.create(content="kept")
    dropped = await Note.query.create(content="dropped", subject=product)

    assert kept.id and dropped.id and product.id

    response = await auth_http.patch(
        f"/api/test_products/{product.id}",
        json={"notes": [["set", [kept.id]]]},
    )
    assert response.status_code == 200, response.text

    linked = await Note.query.filter(subject_model="product", subject_id=product.id).all()
    assert [note.id for note in linked] == [kept.id]
    unlinked = await Note.query.get(id=dropped.id)
    assert unlinked.subject_model is None

    response = await auth_http.patch(f"/api/test_products/{product.id}", json={"notes": [["clear"]]})
    assert response.status_code == 200, response.text
    assert await Note.query.filter(subject_model="product", subject_id=product.id).all() == []
