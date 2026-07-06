# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

import httpx

from fastedgy.test.fixtures import stored_file_path


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
