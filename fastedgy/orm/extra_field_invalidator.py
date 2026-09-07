# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
from contextlib import suppress
from typing import Any

from fastedgy.orm.extra_fields import invalidate_workspace_extra_fields

logger = logging.getLogger("fastedgy.extra_fields")

# The listen connection dies without saying so: a half-open socket (idle NAT
# cut, partition without RST) stays open for hours and silently loses every
# notification. Probed, and the round-trip doubles as a keepalive.
_PROBE_SECONDS = 5.0
_MAX_BACKOFF = 30.0


class ExtraFieldInvalidator:
    """Keeps what every process cached about the declared fields in step.

    A worker holds the fields a workspace declared rather than reading them on
    every request that enters one. Production runs several containers of
    several workers, so the write lands in a process that is not the one
    holding a stale copy: the writer says so on a Postgres channel and every
    listener drops that workspace's entry. Without it, a field an agent has
    just declared would be unknown to the container serving its next call.

    The cache is only trusted while this listener is registered. A channel that
    cannot be opened, or that just died, means reading every time again, which
    is slower and never wrong.
    """

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._listening = False

    @property
    def listening(self) -> bool:
        return self._listening

    async def start(self) -> None:
        if self._task is not None:
            return

        self._stopping.clear()
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        self._stopping.set()
        self._listening = False
        task = self._task
        self._task = None

        if task is not None:
            # A listener caught mid-probe is cancelled rather than waited on:
            # shutting the application down must not hang on a socket that is
            # no longer answering, which is the very case this listener exists
            # to survive.
            with suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=_PROBE_SECONDS)

    def _on_notify(self, connection: Any, pid: int, channel: str, payload: str) -> None:
        try:
            invalidate_workspace_extra_fields(int(payload))
        except ValueError:
            invalidate_workspace_extra_fields()

    async def _connect(self) -> Any:
        """A dedicated connection, never a pooled one: LISTEN holds it for the
        life of the process, and a dead pooled connection cannot be replaced
        from the same task."""
        import asyncpg

        from fastedgy.dependencies import get_service
        from fastedgy.orm import Registry

        url = str(get_service(Registry).database.url)
        scheme, rest = url.split("://", 1)

        return await asyncpg.connect(f"{scheme.split('+')[0]}://{rest}")

    async def _listen(self) -> None:
        backoff = 1.0

        while not self._stopping.is_set():
            connection = None

            try:
                connection = await self._connect()
                await connection.add_listener(self.channel, self._on_notify)

                # Whatever was written while this process was not listening was
                # missed: start from nothing rather than from a stale copy.
                invalidate_workspace_extra_fields()
                self._listening = True
                backoff = 1.0
                logger.info("Listening for workspace extra field changes on '%s'", self.channel)

                await self._hold(connection)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Workspace extra field listener lost: %s", error)
            finally:
                self._listening = False

                if connection is not None:
                    with suppress(Exception):
                        await connection.close()

            if not self._stopping.is_set():
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=backoff)

                backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _hold(self, connection: Any) -> None:
        while not self._stopping.is_set():
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=_PROBE_SECONDS)

            if self._stopping.is_set():
                return

            if connection.is_closed():
                raise ConnectionError("the listen connection was closed by the server")

            await asyncio.wait_for(connection.execute("SELECT 1"), timeout=_PROBE_SECONDS)


__all__ = [
    "ExtraFieldInvalidator",
]
