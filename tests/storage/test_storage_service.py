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
