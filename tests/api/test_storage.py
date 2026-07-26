# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
import os

import httpx

from fastedgy.test.fixtures import stored_file_path


async def _product(name: str = "Laptop") -> int:
    from fastedgy.test.models.product import Product

    product = await Product.query.create(name=name, price="10.00")

    return product.id


async def test_upload_associates_the_attachment_in_one_pass(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    product_id = await _product()

    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
        data={"meta": json.dumps({"record": {"model": "product", "id": product_id}})},
    )

    assert response.status_code == 200

    attachment_id = response.json()["attachments"][0]["id"]
    record = await Attachment.query.get(id=attachment_id)

    # No follow-up PATCH was needed: the polymorphic owner is already set.
    assert record.record_model == "product"
    assert record.record_id == product_id


async def test_upload_accepts_the_serialized_reference_spelling(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    product_id = await _product()

    # "$model" is what a read returns, so echoing a reference back must work.
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
        data={"meta": json.dumps({"record": {"$model": "product", "id": product_id}})},
    )

    assert response.status_code == 200

    record = await Attachment.query.get(id=response.json()["attachments"][0]["id"])

    assert record.record_model == "product"
    assert record.record_id == product_id


async def test_upload_meta_can_target_each_file(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    first = await _product("First")
    second = await _product("Second")

    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files=[
            ("a.txt", ("a.txt", b"aaa", "text/plain")),
            ("b.txt", ("b.txt", b"bbbb", "text/plain")),
        ],
        data={
            "meta": json.dumps(
                {
                    "a.txt": {"record": {"model": "product", "id": first}},
                    "b.txt": {"record": {"model": "product", "id": second}},
                }
            )
        },
    )

    assert response.status_code == 200

    attachments = response.json()["attachments"]
    owners = {}

    for attachment in attachments:
        record = await Attachment.query.get(id=attachment["id"])
        owners[record.name] = record.record_id

    assert owners == {"a": first, "b": second}


async def test_upload_without_meta_keeps_the_attachment_unassociated(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200

    record = await Attachment.query.get(id=response.json()["attachments"][0]["id"])

    assert record.record_model is None
    assert record.record_id is None


async def test_upload_rejects_meta_that_writes_nothing(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    before = await Attachment.query.count()

    # A misspelled per-file key reads as a flat object, whose keys match no
    # Attachment field: the schema would ignore it and the caller would never
    # know its values were dropped.
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
        data={"meta": json.dumps({"doc.pdf": {"record": {"model": "product", "id": 1}}})},
    )

    assert response.status_code == 422
    assert "doc.pdf" in str(response.json()["detail"])
    assert await Attachment.query.count() == before


async def test_upload_rejects_bad_meta_before_storing_anything(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    product_id = await _product()
    before = await Attachment.query.count()
    stored_before = _stored_attachment_files()

    # The second file's values are invalid: the first must not have been stored,
    # otherwise the caller gets a 422 over a half-applied upload.
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files=[
            ("a.txt", ("a.txt", b"aaa", "text/plain")),
            ("b.txt", ("b.txt", b"bbb", "text/plain")),
        ],
        data={
            "meta": json.dumps(
                {
                    "a.txt": {"record": {"model": "product", "id": product_id}},
                    "b.txt": {"record": {"model": "nope", "id": 1}},
                }
            )
        },
    )

    assert response.status_code == 422
    assert await Attachment.query.count() == before
    assert _stored_attachment_files() == stored_before


async def test_upload_rejects_meta_mixing_file_keys_and_values(auth_http: httpx.AsyncClient) -> None:
    product_id = await _product()

    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
        data={
            "meta": json.dumps(
                {
                    "doc.txt": {"record": {"model": "product", "id": product_id}},
                    "name": "ambiguous",
                }
            )
        },
    )

    assert response.status_code == 422


async def test_upload_rejects_invalid_meta_json(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
        data={"meta": "{not json"},
    )

    assert response.status_code == 422


async def test_upload_rejects_a_meta_reference_outside_the_allowed_targets(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    before = await Attachment.query.count()
    stored_before = _stored_attachment_files()

    # "category" is not in the field's `to`: the failure must surface instead of
    # returning a 200 for an attachment that was never associated.
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
        data={"meta": json.dumps({"record": {"model": "category", "id": 1}})},
    )

    assert response.status_code == 422
    assert await Attachment.query.count() == before

    # The bytes were written before the record failed: they must not be left behind.
    assert _stored_attachment_files() == stored_before


def _stored_attachment_files() -> set[str]:
    root = stored_file_path("attachments")

    if not os.path.isdir(root):
        return set()

    return {os.path.join(current, name) for current, _, filenames in os.walk(root) for name in filenames}


async def test_upload_creates_attachment(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200

    attachments = response.json()["attachments"]

    assert len(attachments) == 1

    attachment = attachments[0]

    assert attachment["id"]
    assert attachment["name"] == "doc"
    assert attachment["extension"] == "txt"
    assert attachment["mime_type"] == "text/plain"
    assert attachment["size_bytes"] == len(b"hello world")


async def test_upload_accepts_multiple_files(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post(
        "/api/storage/upload/attachments",
        files=[
            ("a.txt", ("a.txt", b"aaa", "text/plain")),
            ("b.txt", ("b.txt", b"bbbb", "text/plain")),
        ],
    )

    assert response.status_code == 200
    assert len(response.json()["attachments"]) == 2


async def test_upload_then_download_returns_the_content(auth_http: httpx.AsyncClient) -> None:
    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )
    attachment = upload.json()["attachments"][0]

    download = await auth_http.get(f"/api/storage/download/attachments/{attachment['id']}")

    assert download.status_code == 200
    assert download.content == b"hello world"
    assert download.headers["content-type"].startswith("text/plain")


async def test_upload_persists_record_and_file_on_disk(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )
    attachment_id = upload.json()["attachments"][0]["id"]

    # The record exists with a storage path (excluded from the API payload).
    record = await Attachment.query.get(id=attachment_id)
    assert record.storage_path
    assert record.storage_path.startswith("attachments/")

    # The file is physically written at the resolved location with its content.
    full_path = stored_file_path(record.storage_path)
    assert os.path.isfile(full_path)
    with open(full_path, "rb") as handle:
        assert handle.read() == b"hello world"


async def test_delete_attachment_removes_record_and_file(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.attachment import Attachment

    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )
    attachment_id = upload.json()["attachments"][0]["id"]
    full_path = stored_file_path((await Attachment.query.get(id=attachment_id)).storage_path)

    assert os.path.isfile(full_path)

    response = await auth_http.delete(f"/api/attachments/{attachment_id}")

    assert response.status_code in (200, 204)

    # Both the record and the physical file are gone.
    assert (await auth_http.get(f"/api/attachments/{attachment_id}")).status_code == 404
    assert not os.path.exists(full_path)


async def test_delete_attachment_removes_the_file_from_a_workspace_context(auth_http: httpx.AsyncClient) -> None:
    from fastedgy import context
    from fastedgy.test.factories import create_workspace, use_request
    from fastedgy.test.models.attachment import Attachment

    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )
    record = await Attachment.query.get(id=upload.json()["attachments"][0]["id"])
    full_path = stored_file_path(record.storage_path)

    assert os.path.isfile(full_path)

    workspace = await create_workspace(slug="ws-attachment-delete")

    with use_request():
        context.set_workspace(workspace)
        await record.delete()

    assert not os.path.exists(full_path)


async def test_upload_without_files_is_rejected(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.post("/api/storage/upload/attachments", data={"not": "a file"})

    assert response.status_code == 400


async def test_download_unknown_attachment_returns_404(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/storage/download/attachments/999999")

    assert response.status_code == 404


async def test_upload_requires_authentication(setup_http: httpx.AsyncClient) -> None:
    response = await setup_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"x", "text/plain")},
    )

    assert response.status_code == 401


async def test_download_optimized_image_regenerates_evicted_cache(auth_http: httpx.AsyncClient, monkeypatch) -> None:
    import io

    from PIL import Image

    from fastedgy.dependencies import get_service
    from fastedgy.storage import Storage

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(buf, format="PNG")

    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"img.png": ("img.png", buf.getvalue(), "image/png")},
    )
    attachment = upload.json()["attachments"][0]
    url = f"/api/storage/download/attachments/{attachment['id']}?w=32&e=webp"

    first = await auth_http.get(url)
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/webp"

    storage = get_service(Storage)
    real_file_size = storage.cache_adapter.file_size
    evicted = {"done": False}

    async def evicting_file_size(cache_path: str) -> int:
        if not evicted["done"]:
            evicted["done"] = True
            await storage.cache_adapter.delete(cache_path)
            raise FileNotFoundError(cache_path)
        return await real_file_size(cache_path)

    monkeypatch.setattr(storage.cache_adapter, "file_size", evicting_file_size)

    second = await auth_http.get(url)
    assert second.status_code == 200
    assert second.content == first.content


async def test_download_optimized_passthrough_image_is_served(auth_http: httpx.AsyncClient) -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(buf, format="WEBP")

    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"img.webp": ("img.webp", buf.getvalue(), "image/webp")},
    )
    attachment = upload.json()["attachments"][0]

    # Same output format and dimensions clamped to the original size: the
    # generator takes its passthrough path, which used to return a cache
    # path without ever writing the file (FileNotFoundError on every hit).
    response = await auth_http.get(f"/api/storage/download/attachments/{attachment['id']}?w=1080&h=1080&m=cover&e=webp")

    assert response.status_code == 200
    assert response.content == buf.getvalue()

    second = await auth_http.get(f"/api/storage/download/attachments/{attachment['id']}?w=1080&h=1080&m=cover&e=webp")
    assert second.status_code == 200


async def test_attachment_download_revalidates_with_etag(auth_http: httpx.AsyncClient) -> None:
    upload = await auth_http.post(
        "/api/storage/upload/attachments",
        files={"doc.txt": ("doc.txt", b"hello world", "text/plain")},
    )
    attachment = upload.json()["attachments"][0]

    download = await auth_http.get(f"/api/storage/download/attachments/{attachment['id']}")

    assert download.status_code == 200
    assert download.headers["cache-control"] == "private, no-cache"
    etag = download.headers["etag"]
    assert etag.startswith('"attachments/')

    revalidation = await auth_http.get(
        f"/api/storage/download/attachments/{attachment['id']}",
        headers={"If-None-Match": etag},
    )

    assert revalidation.status_code == 304
    assert revalidation.content == b""
    assert revalidation.headers["etag"] == etag
    assert revalidation.headers["cache-control"] == "private, no-cache"


async def test_path_download_is_served_immutable(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.dependencies import get_service
    from fastedgy.storage import Storage

    storage = get_service(Storage)
    await storage.adapter.write("global/cache_headers/pic.txt", b"immutable content")

    download = await auth_http.get("/api/storage/download/cache_headers/pic.txt")

    assert download.status_code == 200
    assert download.content == b"immutable content"
    assert download.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert "etag" not in download.headers
