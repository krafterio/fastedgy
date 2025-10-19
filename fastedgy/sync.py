# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, Generic, Optional, TypeVar

import asyncio
from contextlib import AbstractAsyncContextManager

T = TypeVar("T")


class SyncAsyncContextManager(Generic[T]):
    """
    Wrapper to execute an async context manager synchronously.
    Creates a new event loop, enters the context, allows sync code to run,
    then exits the context and closes the loop.
    """

    def __init__(self, async_cm: AbstractAsyncContextManager[T]) -> None:
        self.async_cm = async_cm
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.entered = False

    def __enter__(self) -> T:
        """Enter the async context manager synchronously"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        result = self.loop.run_until_complete(self.async_cm.__aenter__())
        self.entered = True
        return result

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        """Exit the async context manager synchronously"""
        if self.entered and self.loop is not None:
            try:
                self.loop.run_until_complete(
                    self.async_cm.__aexit__(exc_type, exc_val, exc_tb)
                )
            finally:
                self.loop.close()
                asyncio.set_event_loop(None)

        return False


def run_async_context_sync(
    async_cm: AbstractAsyncContextManager[T],
) -> SyncAsyncContextManager[T]:
    """
    Convert an async context manager to a sync one.

    Usage:
        async_cm = some_async_context_manager()
        with run_async_context_sync(async_cm):
            # sync code here, can even call asyncio.run() internally
            pass
    """
    return SyncAsyncContextManager(async_cm)
