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
