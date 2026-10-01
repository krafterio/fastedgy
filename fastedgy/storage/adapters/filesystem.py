# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import shutil
import time
from collections.abc import AsyncIterator, Callable
from functools import partial
from pathlib import Path
from typing import BinaryIO

from anyio import to_thread

from fastedgy.storage.adapters.base import StorageAdapter, clean_storage_path


class FilesystemAdapter(StorageAdapter):
    """Storage adapter for local filesystem.

    Every read and write of file content runs in a worker thread, so a slow disk never stalls the event loop."""

    def __init__(self, root: str):
        self.root = root

    def _full_path(self, path: str) -> Path:
        safe_parts = Path(clean_storage_path(path)).parts
        return Path(self.root).joinpath(*safe_parts) if safe_parts else Path(self.root)

    @staticmethod
    def _open(full: Path, start: int = 0) -> tuple[BinaryIO, int]:
        file = open(full, "rb")  # noqa: SIM115 - closed by the chunk iterator it is handed to
        if start:
            file.seek(start)
        return file, os.fstat(file.fileno()).st_size

    @staticmethod
    async def _chunks(file: BinaryIO, length: int | None, chunk_size: int) -> AsyncIterator[bytes]:
        try:
            remaining = length
            while remaining is None or remaining > 0:
                size = chunk_size if remaining is None else min(chunk_size, remaining)
                chunk = await to_thread.run_sync(file.read, size)
                if not chunk:
                    break
                if remaining is not None:
                    remaining -= len(chunk)
                yield chunk
        finally:
            file.close()

    def _store(self, path: str, fill: Callable[[BinaryIO], object]) -> None:
        full = self._full_path(path)
        os.makedirs(full.parent, exist_ok=True)
        with open(full, "wb") as target:
            fill(target)

    @staticmethod
    def _delete_older_than(root: Path, cutoff: float) -> int:
        deleted = 0

        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                try:
                    if os.path.getmtime(fpath) < cutoff:
                        os.unlink(fpath)
                        deleted += 1
                except OSError:
                    pass

        # Remove empty directories
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if not filenames and not dirnames:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass

        return deleted

    async def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    async def read(self, path: str) -> bytes:
        return await to_thread.run_sync(self._full_path(path).read_bytes)

    async def read_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        file, _ = await to_thread.run_sync(self._open, self._full_path(path))

        async for chunk in self._chunks(file, None, chunk_size):
            yield chunk

    async def read_range_stream(
        self, path: str, start: int, end: int, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        file, _ = await to_thread.run_sync(self._open, self._full_path(path), start)

        async for chunk in self._chunks(file, end - start + 1, chunk_size):
            yield chunk

    async def open_stream(self, path: str, chunk_size: int = 1024 * 1024) -> tuple[int, AsyncIterator[bytes]]:
        file, size = await to_thread.run_sync(self._open, self._full_path(path))

        return size, self._chunks(file, None, chunk_size)

    async def open_range(
        self, path: str, start: int, end: int | None, chunk_size: int = 1024 * 1024
    ) -> tuple[int, int, int, AsyncIterator[bytes]] | None:
        file, total = await to_thread.run_sync(self._open, self._full_path(path), start)
        last = total - 1 if end is None else min(end, total - 1)

        if start > last:
            file.close()
            return None

        return start, last, total, self._chunks(file, last - start + 1, chunk_size)

    async def write(self, path: str, data: bytes, content_type: str | None = None) -> None:
        await to_thread.run_sync(self._store, path, lambda target: target.write(data))

    async def write_file(self, path: str, file: BinaryIO, content_type: str | None = None) -> None:
        await to_thread.run_sync(self._store, path, lambda target: shutil.copyfileobj(file, target, 1024 * 1024))

    async def delete(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            full.unlink()

    async def delete_directory(self, path: str) -> None:
        await to_thread.run_sync(partial(shutil.rmtree, self._full_path(path), ignore_errors=True))

    async def file_size(self, path: str) -> int:
        return self._full_path(path).stat().st_size

    async def touch(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            os.utime(full)

    async def delete_old_files(self, prefix: str, max_age_seconds: float) -> int:
        root = self._full_path(prefix)
        if not root.exists():
            return 0

        return await to_thread.run_sync(self._delete_older_than, root, time.time() - max_age_seconds)


__all__ = [
    "FilesystemAdapter",
]
