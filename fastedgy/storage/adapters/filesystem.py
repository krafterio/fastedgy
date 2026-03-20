# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import shutil

from pathlib import Path
from typing import AsyncIterator

from fastedgy.storage.adapters.base import StorageAdapter


class FilesystemAdapter(StorageAdapter):
    """Storage adapter for local filesystem."""

    def __init__(self, root: str):
        self.root = root

    def _full_path(self, path: str) -> Path:
        safe_parts = Path(path.strip("/")).parts
        return Path(self.root).joinpath(*safe_parts) if safe_parts else Path(self.root)

    async def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    async def read(self, path: str) -> bytes:
        with open(self._full_path(path), "rb") as f:
            return f.read()

    async def read_stream(
        self, path: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        full = self._full_path(path)
        with open(full, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    async def read_range_stream(
        self, path: str, start: int, end: int, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        full = self._full_path(path)
        remaining = end - start + 1
        with open(full, "rb") as f:
            f.seek(start)
            while remaining > 0:
                to_read = min(chunk_size, remaining)
                chunk = f.read(to_read)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    async def write(
        self, path: str, data: bytes, content_type: str | None = None
    ) -> None:
        full = self._full_path(path)
        os.makedirs(full.parent, exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)

    async def delete(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            full.unlink()

    async def delete_directory(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            shutil.rmtree(full, ignore_errors=True)

    async def file_size(self, path: str) -> int:
        return self._full_path(path).stat().st_size

    async def touch(self, path: str) -> None:
        full = self._full_path(path)
        if full.exists():
            os.utime(full)

    async def delete_old_files(self, prefix: str, max_age_seconds: float) -> int:
        import time

        root = self._full_path(prefix)
        if not root.exists():
            return 0

        cutoff = time.time() - max_age_seconds
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


__all__ = [
    "FilesystemAdapter",
]
