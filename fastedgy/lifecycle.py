# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio


class AppLifecycle:
    """Service to manage application lifecycle and pending operations with a simple lock system"""

    def __init__(self):
        self._locks = 0
        self._lock_event = asyncio.Event()
        self._lock_event.set()  # Initially no locks

    def lock(self) -> None:
        """Lock - indicate that async operations are pending"""
        self._locks += 1
        if self._locks > 0:
            self._lock_event.clear()

    def unlock(self) -> None:
        """Unlock - indicate that async operations are complete"""
        self._locks = max(0, self._locks - 1)
        if self._locks == 0:
            self._lock_event.set()

    async def wait_all_unlocked(self) -> None:
        """Wait until all locks are released (no pending operations)"""
        await self._lock_event.wait()

    @property
    def has_pending(self) -> bool:
        """Check if there are pending operations"""
        return self._locks > 0
