# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from fastedgy.config import BaseSettings

logger = logging.getLogger("fastedgy.realtime.manager")


# Identity, not value: two sockets of the same account in the same workspace are
# two connections, and each index holds them apart.
@dataclass(eq=False)
class Connection:
    """One open socket: who is behind it, and what it asked to hear.

    Both are per socket rather than per account: the workspace is in the URL, so
    one person with two tabs open on two workspaces is two connections, each
    hearing only what its own tab is reading.
    """

    user_id: int
    websocket: Any
    workspace_id: int | None = None
    channels: set[str] = field(default_factory=set)


class WorkspaceChange(NamedTuple):
    """Which workspaces this process started or stopped holding a socket for.

    What the broadcaster listens on follows this: a worker is woken for a
    workspace it serves, and for no other.
    """

    added: int | None = None
    removed: int | None = None


class WebSocketManager:
    """The sockets this process holds, and delivery to them.

    Local only, deliberately: an event has to reach the sockets held by the
    other workers too, and that is [fastedgy.realtime.broadcaster.WebSocketBroadcaster]'s
    job, which comes back here to deliver.

    Connections are indexed by what delivery looks them up by, the workspace and
    the channel, so an event costs what it delivers rather than what the process
    happens to hold.
    """

    def __init__(self, settings: BaseSettings) -> None:
        self._send_timeout = settings.realtime_send_timeout
        self._by_workspace: dict[int, set[Connection]] = {}
        self._by_channel: dict[tuple[int, str], set[Connection]] = {}
        self._by_user: dict[int, set[Connection]] = {}

    @property
    def is_idle(self) -> bool:
        """True when this process holds no socket at all."""
        return not self._by_user

    def workspaces(self) -> list[int]:
        """The workspaces this process holds a socket for."""
        return list(self._by_workspace)

    def connect(self, user_id: int, websocket: Any) -> Connection:
        connection = Connection(user_id=user_id, websocket=websocket)
        self._by_user.setdefault(user_id, set()).add(connection)
        logger.info("WebSocket connected: user_id=%s", user_id)

        return connection

    def disconnect(self, connection: Connection) -> WorkspaceChange:
        change = self._leave_workspace(connection)
        peers = self._by_user.get(connection.user_id)

        if peers is not None:
            peers.discard(connection)

            if not peers:
                del self._by_user[connection.user_id]

        logger.info("WebSocket disconnected: user_id=%s", connection.user_id)

        return change

    def watch(self, connection: Connection, workspace_id: int | None) -> WorkspaceChange:
        """Set which workspace this socket is reading.

        Its subscriptions go with the old one: they named records of a workspace
        this socket has left.
        """
        if connection.workspace_id == workspace_id:
            return WorkspaceChange()

        removed = self._leave_workspace(connection).removed
        connection.workspace_id = workspace_id

        if workspace_id is None:
            return WorkspaceChange(removed=removed)

        holders = self._by_workspace.setdefault(workspace_id, set())
        added = workspace_id if not holders else None
        holders.add(connection)

        return WorkspaceChange(added=added, removed=removed)

    def subscribe(self, connection: Connection, channels: list[str]) -> None:
        for channel in channels:
            connection.channels.add(channel)

            if connection.workspace_id is not None:
                self._by_channel.setdefault((connection.workspace_id, channel), set()).add(connection)

    def unsubscribe(self, connection: Connection, channels: list[str]) -> None:
        for channel in channels:
            connection.channels.discard(channel)
            self._forget_channel(connection, channel)

    async def deliver_to_workspace(
        self,
        workspace_id: int,
        event_type: str,
        data: Any,
        channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> set[int]:
        """Deliver to the local sockets reading this workspace.

        With [channels], only to those subscribed to one of them: a socket hears
        about the records it asked about, not about everything written in the
        workspace. Without, to every socket of the workspace, which is what a
        notice about the workspace itself is.
        """
        if channels is None:
            targets = set(self._by_workspace.get(workspace_id, ()))
        else:
            targets = set()

            for channel in channels:
                targets.update(self._by_channel.get((workspace_id, channel), ()))

        return await self._deliver(targets, event_type, data, meta)

    async def deliver_to_user(
        self,
        user_id: int,
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None = None,
    ) -> set[int]:
        """Deliver to every local socket of one account, whatever it reads."""
        return await self._deliver(set(self._by_user.get(user_id, ())), event_type, data, meta)

    async def _deliver(
        self,
        targets: set[Connection],
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None,
    ) -> set[int]:
        """Send to all of them at once.

        Together rather than one after another: a socket that has stopped
        reading would otherwise hold the event back from everyone behind it in
        the loop.
        """
        if not targets:
            return set()

        ordered = list(targets)
        results = await asyncio.gather(*(self._send(connection, event_type, data, meta) for connection in ordered))

        return {connection.user_id for connection, sent in zip(ordered, results, strict=True) if sent}

    async def _send(
        self,
        connection: Connection,
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        # What is known about the write rather than about the record: which
        # client instance made it, which columns it moved, and whether the
        # payload was left behind on the way (`truncated`, which tells the
        # client to go and read what changed rather than trust what it holds).
        message: dict[str, Any] = {"type": event_type, "data": data, **(meta or {})}

        try:
            async with asyncio.timeout(self._send_timeout):
                await connection.websocket.send_json(message)
        except Exception as e:  # noqa: BLE001 - a socket that cannot take a frame is gone
            # Whatever the client still believes: drop it here rather than on
            # the next event.
            logger.debug("Dropping a dead socket of user %s: %s", connection.user_id, e)
            self.disconnect(connection)

            return False

        return True

    def _leave_workspace(self, connection: Connection) -> WorkspaceChange:
        """Take a socket out of the workspace it was reading, and of its channels."""
        workspace_id = connection.workspace_id

        for channel in list(connection.channels):
            self._forget_channel(connection, channel)

        connection.channels.clear()

        if workspace_id is None:
            return WorkspaceChange()

        holders = self._by_workspace.get(workspace_id)

        if holders is None:
            return WorkspaceChange()

        holders.discard(connection)

        if holders:
            return WorkspaceChange()

        del self._by_workspace[workspace_id]

        return WorkspaceChange(removed=workspace_id)

    def _forget_channel(self, connection: Connection, channel: str) -> None:
        if connection.workspace_id is None:
            return

        key = (connection.workspace_id, channel)
        subscribers = self._by_channel.get(key)

        if subscribers is None:
            return

        subscribers.discard(connection)

        if not subscribers:
            del self._by_channel[key]


__all__ = [
    "Connection",
    "WebSocketManager",
    "WorkspaceChange",
]
