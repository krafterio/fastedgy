# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from fastedgy.test.models.annotation import Annotation
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


async def test_exposed_columns_accept_flat_writes_and_reads(auth_http: httpx.AsyncClient) -> None:
    import json

    product = await _make_product(auth_http, "Pinned")

    response = await auth_http.post(
        "/api/test_notes",
        json={"content": "flat pair", "pinned_model": "product", "pinned_ref": product["id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["pinned_model"] == "product"
    assert response.json()["pinned_ref"] == product["id"]

    note = await Note.query.get(id=response.json()["id"])
    assert note.pinned_model == "product"
    assert note.pinned_ref == product["id"]

    flat_filter = ["pinned_model", "=", "product"]
    filtered = await auth_http.get("/api/test_notes", headers={"X-Filter": json.dumps(flat_filter)})
    assert filtered.status_code == 200, filtered.text
    assert [item["content"] for item in filtered.json()["items"]] == ["flat pair"]


async def test_exposed_columns_validate_the_pair(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http, "Half")

    half = await auth_http.post("/api/test_notes", json={"content": "half", "pinned_model": "product"})
    assert half.status_code == 422, half.text

    mixed = await auth_http.post(
        "/api/test_notes",
        json={
            "content": "mixed",
            "pinned_on": {"model": "product", "id": product["id"]},
            "pinned_model": "product",
            "pinned_ref": product["id"],
        },
    )
    assert mixed.status_code == 422, mixed.text

    unknown = await auth_http.post(
        "/api/test_notes",
        json={"content": "unknown", "pinned_model": "category", "pinned_ref": 1},
    )
    assert unknown.status_code == 422, unknown.text

    both_null = await auth_http.post(
        "/api/test_notes",
        json={"content": "cleared", "pinned_model": None, "pinned_ref": None},
    )
    assert both_null.status_code == 200, both_null.text


async def test_exposed_columns_patch_pair_and_clear(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http, "Repin")
    created = await auth_http.post(
        "/api/test_notes",
        json={"content": "movable", "pinned_model": "product", "pinned_ref": product["id"]},
    )
    note_id = created.json()["id"]

    lone = await auth_http.patch(f"/api/test_notes/{note_id}", json={"pinned_ref": 42})
    assert lone.status_code == 422, lone.text

    cleared = await auth_http.patch(
        f"/api/test_notes/{note_id}",
        json={"pinned_model": None, "pinned_ref": None},
    )
    assert cleared.status_code == 200, cleared.text

    note = await Note.query.get(id=note_id)
    assert note.pinned_model is None
    assert note.pinned_ref is None


async def test_link_and_unlink_ops_on_generic_children(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Linkable", price="9.99")
    note = await Note.query.create(content="free")

    assert product.id and note.id

    linked = await auth_http.patch(f"/api/test_products/{product.id}", json={"notes": [["link", note.id]]})
    assert linked.status_code == 200, linked.text

    fresh = await Note.query.get(id=note.id)
    assert fresh.subject_model == "product"
    assert fresh.subject_id == product.id

    unlinked = await auth_http.patch(f"/api/test_products/{product.id}", json={"notes": [["unlink", note.id]]})
    assert unlinked.status_code == 200, unlinked.text

    fresh = await Note.query.get(id=note.id)
    assert fresh.subject_model is None
    assert fresh.subject_id is None


async def test_update_op_updates_and_links_generic_child(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Updater", price="9.99")
    other = await Product.query.create(name="Elsewhere", price="9.99")
    note = await Note.query.create(content="before", subject=other)

    assert product.id and note.id

    response = await auth_http.patch(
        f"/api/test_products/{product.id}",
        json={"notes": [["update", {"id": note.id, "content": "after"}]]},
    )
    assert response.status_code == 200, response.text

    fresh = await Note.query.get(id=note.id)
    assert fresh.content == "after"
    assert fresh.subject_model == "product"
    assert fresh.subject_id == product.id


async def test_required_reference_create_and_retarget(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http, "Anchored")
    category = await auth_http.post("/api/test_categories", json={"name": "Anchors"})
    category_id = category.json()["id"]

    missing = await auth_http.post("/api/test_annotations", json={"body": "orphan"})
    assert missing.status_code == 422, missing.text

    nulled = await auth_http.post("/api/test_annotations", json={"body": "null anchor", "anchor": None})
    assert nulled.status_code == 422, nulled.text

    created = await auth_http.post(
        "/api/test_annotations",
        json={"body": "pinned", "anchor": {"model": "product", "id": product["id"]}},
    )
    assert created.status_code == 200, created.text
    annotation_id = created.json()["id"]

    annotation = await Annotation.query.get(id=annotation_id)
    assert annotation.anchor_model == "product"
    assert annotation.anchor_id == product["id"]

    retargeted = await auth_http.patch(
        f"/api/test_annotations/{annotation_id}",
        json={"anchor": {"model": "category", "id": category_id}},
    )
    assert retargeted.status_code == 200, retargeted.text

    annotation = await Annotation.query.get(id=annotation_id)
    assert annotation.anchor_model == "category"
    assert annotation.anchor_id == category_id

    cleared = await auth_http.patch(f"/api/test_annotations/{annotation_id}", json={"anchor": None})
    assert cleared.status_code == 422, cleared.text


async def test_required_children_delete_op_skips_the_unlink(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Holder", price="9.99")
    assert product.id
    doomed = await Annotation.query.create(body="doomed", anchor=product)
    kept = await Annotation.query.create(body="kept", anchor=product)

    response = await auth_http.patch(
        f"/api/test_products/{product.id}",
        json={"annotations": [["delete", doomed.id]]},
    )
    assert response.status_code == 200, response.text

    assert await Annotation.query.get_or_none(id=doomed.id) is None
    assert await Annotation.query.get_or_none(id=kept.id) is not None


async def test_required_children_unlink_op_is_rejected(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Sticky", price="9.99")
    assert product.id
    annotation = await Annotation.query.create(body="stuck", anchor=product)

    response = await auth_http.patch(
        f"/api/test_products/{product.id}",
        json={"annotations": [["unlink", annotation.id]]},
    )
    assert response.status_code == 400, response.text

    fresh = await Annotation.query.get(id=annotation.id)
    assert fresh.anchor_model == "product"


async def test_required_children_clear_and_set_delete_the_dropped(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Cleaner", price="9.99")
    assert product.id
    kept = await Annotation.query.create(body="kept", anchor=product)
    dropped = await Annotation.query.create(body="dropped", anchor=product)

    response = await auth_http.patch(
        f"/api/test_products/{product.id}",
        json={"annotations": [["set", [kept.id]]]},
    )
    assert response.status_code == 200, response.text
    assert await Annotation.query.get_or_none(id=dropped.id) is None
    assert await Annotation.query.get_or_none(id=kept.id) is not None

    response = await auth_http.patch(f"/api/test_products/{product.id}", json={"annotations": [["clear"]]})
    assert response.status_code == 200, response.text
    assert await Annotation.query.filter(anchor_model="product", anchor_id=product.id).all() == []


async def test_patch_parent_create_and_delete_generic_children(auth_http: httpx.AsyncClient) -> None:
    product = await Product.query.create(name="Ops", price="9.99")
    doomed = await Note.query.create(content="doomed", subject=product)

    assert product.id and doomed.id

    response = await auth_http.patch(
        f"/api/test_products/{product.id}",
        json={"notes": [["create", {"content": "born"}], ["delete", doomed.id]]},
    )
    assert response.status_code == 200, response.text

    remaining = await Note.query.filter(subject_model="product", subject_id=product.id).all()
    assert [note.content for note in remaining] == ["born"]
    assert await Note.query.get_or_none(id=doomed.id) is None


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
