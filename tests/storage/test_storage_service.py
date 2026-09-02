# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.storage import Storage
from fastedgy.test.fixtures import stored_file_path


async def test_write_read_and_size(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)

    await storage.adapter.write("global/note.txt", b"hello")

    assert await storage.file_exists("note.txt", global_storage=True) is True
    assert await storage.read_file("note.txt", global_storage=True) == b"hello"
    assert await storage.file_size("note.txt", global_storage=True) == 5


async def test_file_lands_on_disk_under_global_prefix(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)

    await storage.adapter.write("global/folder/doc.txt", b"data")

    assert os.path.isfile(stored_file_path("folder/doc.txt"))


async def test_delete_removes_file(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)

    await storage.adapter.write("global/temp.txt", b"bye")
    assert os.path.isfile(stored_file_path("temp.txt"))

    await storage.delete("temp.txt", global_storage=True)

    assert await storage.file_exists("temp.txt", global_storage=True) is False
    assert not os.path.exists(stored_file_path("temp.txt"))


async def test_undecodable_image_falls_back_to_the_original(setup_db: FastEdgy, caplog) -> None:
    import logging

    storage = get_service(Storage)

    await storage.adapter.write("global/photos/broken.jpg", b"definitely not a jpeg")

    with caplog.at_level(logging.WARNING, logger="fastedgy.storage"):
        resolved, mime = await storage.get_optimized_or_original("photos/broken.jpg", w=100, h=100, global_storage=True)

    assert resolved == "photos/broken.jpg"
    assert mime == "image/jpeg"
    assert any("serving the original" in r.getMessage() for r in caplog.records)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


async def test_oversized_image_falls_back_to_the_original(setup_db: FastEdgy, caplog, monkeypatch) -> None:
    import io
    import logging

    from PIL import Image

    storage = get_service(Storage)

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, "JPEG")
    await storage.adapter.write("global/photos/huge.jpg", buf.getvalue())

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)

    with caplog.at_level(logging.WARNING, logger="fastedgy.storage"):
        resolved, mime = await storage.get_optimized_or_original("photos/huge.jpg", w=50, h=50, global_storage=True)

    assert resolved == "photos/huge.jpg"
    assert mime == "image/jpeg"
    assert any("serving the original" in r.getMessage() for r in caplog.records)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


async def test_upload_refuses_an_image_over_pillow_ceiling(setup_db: FastEdgy, monkeypatch) -> None:
    import io

    import pytest
    from PIL import Image

    storage = get_service(Storage)

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, "JPEG")

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)

    with pytest.raises(ValueError):
        await storage.upload_from_bytes(
            buf.getvalue(), "photos", filename="bomb.{ext}", mime_type="image/jpeg", global_storage=True
        )

    assert not os.path.exists(stored_file_path("photos/bomb.jpg"))


async def test_upload_refuses_an_image_over_the_configured_budget(setup_db: FastEdgy, monkeypatch) -> None:
    import io

    import pytest
    from PIL import Image

    storage = get_service(Storage)

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, "JPEG")

    monkeypatch.setattr(storage.settings, "image_max_pixels", 9999)

    with pytest.raises(ValueError):
        await storage.upload_from_bytes(
            buf.getvalue(), "photos", filename="big.{ext}", mime_type="image/jpeg", global_storage=True
        )

    assert not os.path.exists(stored_file_path("photos/big.jpg"))

    monkeypatch.setattr(storage.settings, "image_max_pixels", 10001)
    await storage.upload_from_bytes(
        buf.getvalue(), "photos", filename="big.{ext}", mime_type="image/jpeg", global_storage=True
    )

    assert os.path.isfile(stored_file_path("photos/big.jpg"))


async def test_upload_of_a_non_image_is_left_alone(setup_db: FastEdgy, monkeypatch) -> None:
    from PIL import Image

    storage = get_service(Storage)

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)

    await storage.upload_from_bytes(
        b"%PDF-1.4 not an image at all",
        "docs",
        filename="report.{ext}",
        mime_type="application/pdf",
        global_storage=True,
    )

    assert os.path.isfile(stored_file_path("docs/report.pdf"))


async def test_delete_workspace_takes_an_explicit_id(setup_db: FastEdgy) -> None:
    from fastedgy.test.fixtures import STORAGE_ROOT

    storage = get_service(Storage)

    await storage.adapter.write("workspace/42/notes/a.txt", b"data")
    await storage.cache_adapter.write("cache_optimized_images/workspace/42/thumb.webp", b"cache")

    assert await storage.delete_workspace(42) is True

    assert not os.path.exists(os.path.join(STORAGE_ROOT, "workspace", "42"))
    assert not os.path.exists(os.path.join(STORAGE_ROOT, "cache_optimized_images", "workspace", "42"))


async def test_delete_workspace_without_workspace_does_nothing(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)

    assert await storage.delete_workspace() is False
