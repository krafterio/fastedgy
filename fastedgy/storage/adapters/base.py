# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod
from typing import AsyncIterator


class StorageAdapter(ABC):
    """Abstract base class for storage adapters."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists at the given path."""
        ...

    @abstractmethod
    async def read(self, path: str) -> bytes:
        """Read the entire file content as bytes."""
        ...

    @abstractmethod
    async def read_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        """Stream file content in chunks."""
        ...
        yield b""  # pragma: no cover - make it a valid async generator

    @abstractmethod
    async def write(self, path: str, data: bytes, content_type: str | None = None) -> None:
        """Write data to a file at the given path."""
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file at the given path. No error if the file doesn't exist."""
        ...

    @abstractmethod
    async def delete_directory(self, path: str) -> None:
        """Delete a directory and all its contents. No error if it doesn't exist."""
        ...

    @abstractmethod
    async def read_range_stream(
        self, path: str, start: int, end: int, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        """Stream a byte range of the file (inclusive start and end)."""
        ...
        yield b""  # pragma: no cover - make it a valid async generator

    @abstractmethod
    async def file_size(self, path: str) -> int:
        """Return the size of the file in bytes."""
        ...


__all__ = [
    "StorageAdapter",
]
