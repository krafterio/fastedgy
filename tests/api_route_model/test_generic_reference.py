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


async def test_reference_flat_columns_still_accepted(auth_http: httpx.AsyncClient) -> None:
    product = await _make_product(auth_http)

    response = await auth_http.post(
        "/api/test_notes",
        json={"content": "flat", "subject_model": "product", "subject_id": product["id"]},
    )
    assert response.status_code == 200, response.text

    note = await Note.query.get(id=response.json()["id"])
    assert note.subject_model == "product"
    assert note.subject_id == product["id"]


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
