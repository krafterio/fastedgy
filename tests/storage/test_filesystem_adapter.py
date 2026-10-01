# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import time
from pathlib import Path

import pytest

from fastedgy.storage.adapters.filesystem import FilesystemAdapter


@pytest.fixture
def adapter(tmp_path: Path) -> FilesystemAdapter:
    return FilesystemAdapter(str(tmp_path))


async def test_open_stream_gives_the_size_then_the_content(adapter: FilesystemAdapter) -> None:
    await adapter.write("a/notes.txt", b"hello world")

    size, chunks = await adapter.open_stream("a/notes.txt", chunk_size=4)

    assert size == 11
    assert [chunk async for chunk in chunks] == [b"hell", b"o wo", b"rld"]


async def test_a_range_reads_only_its_bytes(adapter: FilesystemAdapter) -> None:
    await adapter.write("a/notes.txt", b"hello world")

    assert [chunk async for chunk in adapter.read_range_stream("a/notes.txt", 4, 6, chunk_size=2)] == [b"o ", b"w"]


async def test_a_missing_file_is_not_found(adapter: FilesystemAdapter) -> None:
    with pytest.raises(FileNotFoundError):
        await adapter.open_stream("nowhere.txt")


async def test_old_files_then_the_directory_are_removed(adapter: FilesystemAdapter, tmp_path: Path) -> None:
    await adapter.write("cache/old.bin", b"1")
    await adapter.write("cache/new.bin", b"2")
    old = tmp_path / "cache" / "old.bin"
    past = time.time() - 7200
    os.utime(old, (past, past))

    assert await adapter.delete_old_files("cache", max_age_seconds=3600) == 1
    assert not old.exists()
    assert (tmp_path / "cache" / "new.bin").exists()

    await adapter.delete_directory("cache")

    assert not (tmp_path / "cache").exists()


async def test_open_range_serves_the_rest_of_the_file(adapter: FilesystemAdapter) -> None:
    await adapter.write("a/digits.txt", b"0123456789")

    opened = await adapter.open_range("a/digits.txt", 5, None)

    assert opened is not None
    start, end, total, chunks = opened
    assert (start, end, total) == (5, 9, 10)
    assert [chunk async for chunk in chunks] == [b"56789"]


async def test_open_range_past_the_end_opens_nothing(adapter: FilesystemAdapter) -> None:
    await adapter.write("a/digits.txt", b"0123456789")

    assert await adapter.open_range("a/digits.txt", 50, None) is None
    assert await adapter.open_range("a/digits.txt", 5, 2) is None
