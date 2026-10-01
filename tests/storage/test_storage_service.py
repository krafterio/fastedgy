# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
import os
import time
from pathlib import Path

import pytest

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.storage import FilesystemAdapter, Storage, StorageUsage
from fastedgy.test.fixtures import STORAGE_ROOT, stored_file_path


def _png(color: str) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")

    return buf.getvalue()


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


async def test_upload_streams_the_file_to_the_adapter(setup_db: FastEdgy, monkeypatch) -> None:
    from tempfile import SpooledTemporaryFile
    from typing import BinaryIO, cast

    from starlette.datastructures import Headers, UploadFile

    storage = get_service(Storage)

    async def held_in_memory(*args, **kwargs) -> None:
        raise AssertionError("the upload was read whole before being stored")

    monkeypatch.setattr(storage.adapter, "write", held_in_memory)

    with SpooledTemporaryFile(max_size=1024) as spooled:
        spooled.write(b"x" * 4096)
        spooled.seek(0)
        upload = UploadFile(
            file=cast(BinaryIO, spooled), filename="clip.mp4", headers=Headers({"content-type": "video/mp4"})
        )

        path = await storage.upload(upload, "videos", filename="clip.{ext}", global_storage=True)

    assert path == "videos/clip.mp4"
    assert await storage.read_file(path, global_storage=True) == b"x" * 4096


async def test_a_cached_variant_is_served_without_touching_the_source(setup_db: FastEdgy, monkeypatch) -> None:
    import io

    from PIL import Image

    storage = get_service(Storage)
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "green").save(buf, format="PNG")
    await storage.adapter.write("global/photos/green.png", buf.getvalue())

    first, _ = await storage.get_optimized_or_original("photos/green.png", w=32, global_storage=True)
    assert first.startswith("__cache__:")

    async def touched(*args, **kwargs):
        raise AssertionError("the source was reached for a cached variant")

    monkeypatch.setattr(storage.adapter, "exists", touched)
    monkeypatch.setattr(storage.adapter, "read", touched)

    second, mime = await storage.get_optimized_or_original("photos/green.png", w=32, global_storage=True)

    assert second == first
    assert mime == "image/png"


async def test_a_route_resolution_leaves_the_cache_unasked(setup_db: FastEdgy, monkeypatch) -> None:
    storage = get_service(Storage)

    async def asked(*args, **kwargs):
        raise AssertionError("the cache was asked before being read")

    monkeypatch.setattr(storage.cache_adapter, "exists", asked)

    resolved, mime = await storage.get_optimized_or_original(
        "photos/never.png", w=32, global_storage=True, check_cache=False
    )

    assert resolved == "__cache__:cache_optimized_images/global/photos/never.png/contain_w32_h0.png"
    assert mime == "image/png"


async def test_reading_a_cached_variant_refreshes_its_date(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)
    await storage.adapter.write("global/photos/blue.png", _png("blue"))
    resolved, _ = await storage.get_optimized_or_original("photos/blue.png", w=32, global_storage=True)
    cached = Path(STORAGE_ROOT) / resolved.removeprefix("__cache__:")
    stamp = time.time() - 10 * 86400
    os.utime(cached, (stamp, stamp))

    _, chunks = await storage.open_download(resolved, global_storage=True)
    assert b"".join([chunk async for chunk in chunks])

    assert cached.stat().st_mtime > stamp + 86400


@pytest.fixture
def cache(monkeypatch, tmp_path: Path) -> FilesystemAdapter:
    adapter = FilesystemAdapter(str(tmp_path))
    monkeypatch.setattr(get_service(Storage), "cache_adapter", adapter)

    return adapter


async def _aged(cache: FilesystemAdapter, path: str, days: float) -> Path:
    await cache.write(path, b"x")
    full = Path(cache.root) / path
    stamp = time.time() - days * 86400
    os.utime(full, (stamp, stamp))

    return full


async def test_cleanup_image_cache_drops_what_is_older_than_30_days_by_default(
    setup_db: FastEdgy, cache: FilesystemAdapter
) -> None:
    old = await _aged(cache, "cache_optimized_images/global/old.png/contain_w32_h0.png", 31)
    recent = await _aged(cache, "cache_optimized_images/global/new.png/contain_w32_h0.png", 29)
    storage = get_service(Storage)

    assert storage.settings.storage_cache_max_age_days == 30
    assert await storage.cleanup_image_cache() == 1
    assert not old.exists()
    assert recent.exists()


async def test_cleanup_image_cache_keeps_everything_at_zero(
    setup_db: FastEdgy, cache: FilesystemAdapter, override_settings
) -> None:
    override_settings(storage_cache_max_age_days=0)
    old = await _aged(cache, "cache_optimized_images/global/old.png/contain_w32_h0.png", 400)

    assert await get_service(Storage).cleanup_image_cache() == 0
    assert old.exists()


async def test_usage_counts_files_and_cache_in_one_walk_when_they_share_a_store(
    setup_db: FastEdgy, monkeypatch, tmp_path: Path
) -> None:
    storage = get_service(Storage)
    files = FilesystemAdapter(str(tmp_path))
    monkeypatch.setattr(storage, "adapter", files)
    monkeypatch.setattr(storage, "cache_adapter", FilesystemAdapter(str(tmp_path)))
    await files.write("workspace/1/a.txt", b"hello")
    await files.write("global/b.txt", b"abc")
    await files.write("cache_optimized_images/global/b.png/contain_w32_h0.png", b"xy")

    async def walked_twice(*args, **kwargs):
        raise AssertionError("the shared store was walked twice")

    monkeypatch.setattr(storage.cache_adapter, "usage", walked_twice)

    assert await storage.usage() == StorageUsage(data_files=2, data_bytes=8, cache_files=1, cache_bytes=2)


async def test_usage_reads_a_cache_kept_in_another_store(setup_db: FastEdgy, monkeypatch, tmp_path: Path) -> None:
    storage = get_service(Storage)
    files = FilesystemAdapter(str(tmp_path / "files"))
    cache = FilesystemAdapter(str(tmp_path / "cache"))
    monkeypatch.setattr(storage, "adapter", files)
    monkeypatch.setattr(storage, "cache_adapter", cache)
    await files.write("global/b.txt", b"abc")
    await cache.write("cache_optimized_images/global/b.png/contain_w32_h0.png", b"xy")
    await cache.write("exports/not-cache.csv", b"zzz")

    assert await storage.usage() == StorageUsage(data_files=1, data_bytes=3, cache_files=1, cache_bytes=2)


async def test_a_download_token_opens_the_key_it_was_signed_for(setup_db: FastEdgy) -> None:
    storage = get_service(Storage)

    stored = storage.download_token("videos/clip.mp4", global_storage=True)
    cached = storage.download_token("__cache__:cache_optimized_images/global/a.png/contain_w32_h0.webp")

    assert storage.resolve_download_token(stored) == "__stored__:global/videos/clip.mp4"
    assert storage.resolve_download_token(cached) == "__cache__:cache_optimized_images/global/a.png/contain_w32_h0.webp"
    assert storage.resolve_download_token(stored[:-2] + "xx") is None
