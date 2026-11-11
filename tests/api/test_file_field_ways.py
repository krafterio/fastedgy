# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""A file field takes its file from the upload route or as a data URL written by the API, and loses it through the
delete route or a null written by the API. Both ways run the same code: each scenario below is played by the two
and must end the same."""

import base64
import os
import re
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import (
    PostDeleteFileTransformer,
    PostSaveTransformer,
    PostUploadTransformer,
    PreDeleteFileTransformer,
    PreSaveTransformer,
    PreUploadTransformer,
)
from fastedgy.dependencies import get_service
from fastedgy.orm.fields import StoredImage
from fastedgy.orm.signals import post_save
from fastedgy.storage import Storage
from fastedgy.test.factories import run_queued_tasks
from fastedgy.test.fixtures import STORAGE_ROOT, stored_file_path
from fastedgy.test.images import described_image, encoded_image
from fastedgy.test.models.product import Product

WAYS = ("route", "api")


def _png(size: tuple[int, int] = (3000, 1500)) -> bytes:
    return encoded_image(size, "png", (255, 0, 0))


def _shape(path: str | None) -> str | None:
    return re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", "<uuid>", path) if path else path


def _cache(path: str) -> str:
    return os.path.join(STORAGE_ROOT, "cache_optimized_images", "global", path)


def _stored_files() -> set[str]:
    directory = stored_file_path("product")

    return set(os.listdir(directory)) if os.path.isdir(directory) else set()


async def _product() -> int:
    return (await Product.query.create(name="Laptop", price="10.00")).id


async def _image(product_id: int) -> str | None:
    return (await Product.query.get(id=product_id)).image


async def _write(
    client: httpx.AsyncClient, way: str, product_id: int, data: bytes, name: str, content_type: str
) -> httpx.Response:
    if way == "route":
        return await client.post(
            f"/api/storage/upload/product/{product_id}/image", files={"file": (name, data, content_type)}
        )

    data_url = f"data:{content_type};base64,{base64.b64encode(data).decode()}"

    return await client.patch(f"/api/test_products/{product_id}", json={"image": data_url})


async def _clear(client: httpx.AsyncClient, way: str, product_id: int) -> httpx.Response:
    if way == "route":
        return await client.delete(f"/api/storage/file/product/{product_id}/image")

    return await client.patch(f"/api/test_products/{product_id}", json={"image": None})


async def _with_cached_image(client: httpx.AsyncClient) -> tuple[int, str]:
    product_id = await _product()
    await _write(client, "route", product_id, _png((40, 20)), "first.png", "image/png")
    path = await _image(product_id)
    assert path is not None
    await get_service(Storage).get_optimized_or_original(path, w=10, global_storage=True)
    assert os.path.isdir(_cache(path))

    return product_id, path


@pytest.fixture
def hooks() -> Iterator[list[str]]:
    calls: list[str] = []

    class Recorder(
        PreUploadTransformer,
        PostUploadTransformer,
        PreDeleteFileTransformer,
        PostDeleteFileTransformer,
        PreSaveTransformer,
        PostSaveTransformer,
    ):
        async def pre_upload(self, request, record, field, file, ctx) -> None:
            calls.append(f"pre_upload {field} {file.content_type}")

        async def post_upload(self, request, record, field, path, ctx) -> str:
            calls.append(f"post_upload {field}")

            return path

        async def pre_delete_file(self, request, model, model_id, field, record, ctx) -> None:
            calls.append(f"pre_delete_file {field}")

        async def post_delete_file(self, request, model, model_id, field, record, ctx) -> None:
            calls.append(f"post_delete_file {field}")

        async def pre_save(self, request, item, item_data, ctx, created) -> None:
            calls.append(f"pre_save {sorted(item_data.model_fields_set)}")

        async def post_save(self, request, item, item_data, ctx, created) -> None:
            calls.append("post_save")

    async def saved(sender: Any, instance: Any, **_: Any) -> None:
        calls.append("signal post_save")

    ViewTransformerRegistry._transformers.pop(Product, None)
    get_service(ViewTransformerRegistry).register_transformer(Recorder, Product)

    try:
        with post_save.connected_to(saved, sender=Product):
            yield calls
    finally:
        ViewTransformerRegistry._transformers.pop(Product, None)


async def test_adding_a_file_ends_the_same_both_ways(auth_http: httpx.AsyncClient, hooks: list[str]) -> None:
    results = {}

    for way in WAYS:
        product_id = await _product()
        hooks.clear()
        response = await _write(auth_http, way, product_id, _png(), "photo.png", "image/png")
        path = await _image(product_id)
        assert response.status_code == 200, response.text
        assert path is not None
        stored = described_image(stored_file_path(path))
        results[way] = (_shape(path), *stored, list(hooks))

    assert results["route"] == results["api"]
    assert results["api"][:3] == ("product/<uuid>.webp", "WEBP", (2560, 1280))


async def test_a_data_url_at_creation_is_stored_like_an_upload(auth_http: httpx.AsyncClient) -> None:
    uploaded = await _product()
    await _write(auth_http, "route", uploaded, _png(), "photo.png", "image/png")
    data_url = f"data:image/png;base64,{base64.b64encode(_png()).decode()}"
    created = await auth_http.post("/api/test_products", json={"name": "Laptop", "price": "10.00", "image": data_url})
    paths = [await _image(uploaded), await _image(created.json()["id"])]

    assert [_shape(path) for path in paths] == ["product/<uuid>.webp"] * 2
    assert [described_image(stored_file_path(str(path)))[1] for path in paths] == [(2560, 1280)] * 2


@pytest.mark.parametrize("segment", ["product", "test_products"])
async def test_an_upload_is_stored_under_the_model_whichever_name_the_route_takes(
    auth_http: httpx.AsyncClient, segment: str
) -> None:
    product_id = await _product()

    response = await auth_http.post(
        f"/api/storage/upload/{segment}/{product_id}/image", files={"file": ("a.png", _png((40, 20)), "image/png")}
    )

    assert response.status_code == 200, response.text
    assert _shape(await _image(product_id)) == "product/<uuid>.webp"


async def test_replacing_a_file_ends_the_same_both_ways(auth_http: httpx.AsyncClient, hooks: list[str]) -> None:
    results = {}

    for way in WAYS:
        product_id, previous = await _with_cached_image(auth_http)
        hooks.clear()
        response = await _write(auth_http, way, product_id, _png(), "photo.png", "image/png")
        await run_queued_tasks()
        path = await _image(product_id)
        assert response.status_code == 200, response.text
        results[way] = (
            _shape(path),
            path != previous,
            os.path.exists(stored_file_path(previous)),
            os.path.exists(_cache(previous)),
            list(hooks),
        )

    assert results["route"] == results["api"]
    assert results["api"][:4] == ("product/<uuid>.webp", True, False, False)


async def test_removing_a_file_ends_the_same_both_ways(auth_http: httpx.AsyncClient, hooks: list[str]) -> None:
    results = {}

    for way in WAYS:
        product_id, previous = await _with_cached_image(auth_http)
        hooks.clear()
        response = await _clear(auth_http, way, product_id)
        await run_queued_tasks()
        assert response.is_success, response.text
        results[way] = (
            await _image(product_id),
            os.path.exists(stored_file_path(previous)),
            os.path.exists(_cache(previous)),
            list(hooks),
        )

    assert results["route"] == results["api"]
    assert results["api"][:3] == (None, False, False)


@pytest.mark.parametrize("case", ["refused type", "too large", "too many pixels"])
async def test_a_refused_file_answers_the_same_both_ways(
    auth_http: httpx.AsyncClient, override_settings, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    data, name, content_type = _png((40, 20)), "photo.png", "image/png"

    if case == "refused type":
        data, name, content_type = b"<svg onload=alert(1)>", "logo.svg", "image/svg+xml"
    elif case == "too large":
        override_settings(storage_max_upload_size=10)
    else:
        monkeypatch.setattr(Product.meta.fields["image"], "stored_image", StoredImage(max_pixels=100))

    results = {}

    for way in WAYS:
        product_id = await _product()
        before = _stored_files()
        response = await _write(auth_http, way, product_id, data, name, content_type)
        results[way] = (response.status_code, response.json(), _stored_files() == before, await _image(product_id))

    assert results["route"] == results["api"]
    assert results["api"][0] == 422 and results["api"][2:] == (True, None)


async def test_a_record_left_unwritten_keeps_no_new_file_both_ways(auth_http: httpx.AsyncClient) -> None:
    class Frozen(PreSaveTransformer):
        async def pre_save(self, request, item, item_data, ctx, created) -> None:
            raise HTTPException(status_code=403, detail="frozen")

    results = {}
    ViewTransformerRegistry._transformers.pop(Product, None)
    get_service(ViewTransformerRegistry).register_transformer(Frozen, Product)

    try:
        for way in WAYS:
            product_id = await _product()
            before = _stored_files()
            response = await _write(auth_http, way, product_id, _png((40, 20)), "photo.png", "image/png")
            results[way] = (response.status_code, response.json(), _stored_files() == before, await _image(product_id))
    finally:
        ViewTransformerRegistry._transformers.pop(Product, None)

    assert results["route"] == results["api"] == (403, {"detail": "frozen"}, True, None)


async def test_a_refusing_transformer_has_its_writes_rolled_back_both_ways(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.tag import Tag

    class Refusing(PreUploadTransformer):
        async def pre_upload(self, request, record, field, file, ctx) -> None:
            await Tag.query.create(name=f"written before refusing {record.id}")

            raise HTTPException(status_code=403, detail="refused")

    results = {}
    ViewTransformerRegistry._transformers.pop(Product, None)
    get_service(ViewTransformerRegistry).register_transformer(Refusing, Product)

    try:
        for way in WAYS:
            product_id = await _product()
            response = await _write(auth_http, way, product_id, _png((40, 20)), "photo.png", "image/png")
            results[way] = (response.status_code, response.json(), await Tag.query.count())
    finally:
        ViewTransformerRegistry._transformers.pop(Product, None)

    assert results["route"] == results["api"] == (403, {"detail": "refused"}, 0)
