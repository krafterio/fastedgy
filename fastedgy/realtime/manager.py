# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import contextlib
import logging
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from fastapi import status

from fastedgy.config import BaseSettings

logger = logging.getLogger("fastedgy.realtime.manager")


# Identity, not value: two sockets of the same account in the same scope are two
# connections, and each index holds them apart.
@dataclass(eq=False)
class Connection:
    """One open socket: who is behind it, and what it asked to hear.

    Both are per socket rather than per account: the scope is in the URL, so one
    person with two tabs open on two scopes is two connections, each hearing only
    what its own tab is reading.

    `asked_scope` is the scope as the client named it, resolved again each time
    the socket is checked; setting `recheck` asks for that check now.
    """

    user_id: int
    websocket: Any
    scope_id: int | None = None
    asked_scope: Any = None
    channels: set[str] = field(default_factory=set)
    state: dict[str, Any] = field(default_factory=dict)
    recheck: asyncio.Event = field(default_factory=asyncio.Event)


class ScopeChange(NamedTuple):
    """Which scopes this process started or stopped holding a socket for.

    What the broadcaster listens on follows this: a worker is woken for a scope it
    serves, and for no other.
    """

    added: int | None = None
    removed: int | None = None


class WebSocketManager:
    """The sockets this process holds, and delivery to them.

    Local only, deliberately: an event has to reach the sockets held by the
    other workers too, and that is [fastedgy.realtime.broadcaster.WebSocketBroadcaster]'s
    job, which comes back here to deliver.

    Connections are indexed by what delivery looks them up by, the scope and the
    channel, so an event costs what it delivers rather than what the process
    happens to hold.
    """

    def __init__(self, settings: BaseSettings) -> None:
        self._send_timeout = settings.realtime_send_timeout
        self._max_channels = settings.realtime_max_channels
        self._by_scope: dict[int, set[Connection]] = {}
        self._by_channel: dict[tuple[int, str], set[Connection]] = {}
        self._by_user: dict[int, set[Connection]] = {}
        self._closing: set[asyncio.Task] = set()

    @property
    def is_idle(self) -> bool:
        """True when this process holds no socket at all."""
        return not self._by_user

    def scopes(self) -> list[int]:
        """The scopes this process holds a socket for."""
        return list(self._by_scope)

    def count(self, user_id: int) -> int:
        """How many sockets this process holds for one account."""
        return len(self._by_user.get(user_id, ()))

    def holders(
        self,
        scope_id: int,
        channels: list[str] | None = None,
        exclude_user_ids: Collection[int] | None = None,
    ) -> set[int]:
        """The accounts a delivery to this scope would reach on this process."""
        return {connection.user_id for connection in self._scope_targets(scope_id, channels, exclude_user_ids)}

    def connect(self, user_id: int, websocket: Any) -> Connection:
        connection = Connection(user_id=user_id, websocket=websocket)
        self._by_user.setdefault(user_id, set()).add(connection)
        logger.info("WebSocket connected: user_id=%s", user_id)

        return connection

    def disconnect(self, connection: Connection) -> ScopeChange:
        change = self._leave_scope(connection)
        peers = self._by_user.get(connection.user_id)

        if peers is not None:
            peers.discard(connection)

            if not peers:
                del self._by_user[connection.user_id]

        logger.info("WebSocket disconnected: user_id=%s", connection.user_id)

        return change

    def watch(self, connection: Connection, scope_id: int | None) -> ScopeChange:
        """Set which scope this socket is reading.

        Its subscriptions go with the old one: they named records of a scope this
        socket has left.
        """
        if connection.scope_id == scope_id:
            return ScopeChange()

        removed = self._leave_scope(connection).removed
        connection.scope_id = scope_id

        if scope_id is None:
            return ScopeChange(removed=removed)

        holders = self._by_scope.setdefault(scope_id, set())
        added = scope_id if not holders else None
        holders.add(connection)

        return ScopeChange(added=added, removed=removed)

    def subscribe(self, connection: Connection, channels: list[str]) -> None:
        """Have a socket hear about these channels, up to as many as one may hold.

        What a client asks for past [BaseSettings.realtime_max_channels] is
        ignored: a socket is no place to keep whatever a client invents.
        """
        for channel in channels:
            if channel not in connection.channels and len(connection.channels) >= self._max_channels:
                logger.debug("A socket of user %s holds as many channels as it may", connection.user_id)

                return

            connection.channels.add(channel)

            if connection.scope_id is not None:
                self._by_channel.setdefault((connection.scope_id, channel), set()).add(connection)

    def unsubscribe(self, connection: Connection, channels: list[str]) -> None:
        for channel in channels:
            connection.channels.discard(channel)
            self._forget_channel(connection, channel)

    def watchers(self, user_ids: Iterable[int], channels: Collection[str]) -> dict[int, set[str]]:
        wanted = set(channels)
        found: dict[int, set[str]] = {}

        for user_id in user_ids:
            for connection in self._by_user.get(user_id, ()):
                matched = connection.channels & wanted

                if matched:
                    found.setdefault(user_id, set()).update(matched)

        return found

    def recheck(self, user_ids: Iterable[int]) -> None:
        """Have the sockets of these accounts check again what they were let in with."""
        for user_id in user_ids:
            for connection in self._by_user.get(user_id, ()):
                connection.recheck.set()

    async def deliver_to_scope(
        self,
        scope_id: int,
        event_type: str,
        data: Any,
        channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        exclude_user_ids: Collection[int] | None = None,
        only_user_ids: Collection[int] | None = None,
    ) -> set[int]:
        """Deliver to the local sockets reading this scope.

        With [channels], only to those subscribed to one of them: a socket hears
        about the records it asked about, not about everything written in the
        scope. Without, to every socket of the scope, which is what a notice about
        the scope itself is. Never to the sockets of [exclude_user_ids], and with
        [only_user_ids], to the sockets of those accounts alone.
        """
        targets = self._scope_targets(scope_id, channels, exclude_user_ids)

        if only_user_ids is not None:
            allowed = set(only_user_ids)
            targets = {connection for connection in targets if connection.user_id in allowed}

        return await self._deliver(targets, event_type, data, meta)

    def _scope_targets(
        self,
        scope_id: int,
        channels: list[str] | None,
        exclude_user_ids: Collection[int] | None,
    ) -> set[Connection]:
        if channels is None:
            targets = set(self._by_scope.get(scope_id, ()))
        else:
            targets = set()

            for channel in channels:
                targets.update(self._by_channel.get((scope_id, channel), ()))

        if exclude_user_ids:
            targets = {connection for connection in targets if connection.user_id not in exclude_user_ids}

        return targets

    async def deliver_to_users(
        self,
        user_ids: Iterable[int],
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None = None,
    ) -> set[int]:
        targets: set[Connection] = set()

        for user_id in user_ids:
            targets.update(self._by_user.get(user_id, ()))

        return await self._deliver(targets, event_type, data, meta)

    async def deliver_to_user(
        self,
        user_id: int,
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None = None,
    ) -> set[int]:
        """Deliver to every local socket of one account, whatever it reads."""
        return await self.deliver_to_users([user_id], event_type, data, meta)

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
            logger.debug("Dropping a dead socket of user %s: %s", connection.user_id, e)
            self.disconnect(connection)
            self._close(connection.websocket)

            return False

        return True

    def _close(self, websocket: Any) -> None:
        task = asyncio.create_task(self._close_socket(websocket))
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)

    async def _close_socket(self, websocket: Any) -> None:
        with contextlib.suppress(Exception):
            async with asyncio.timeout(self._send_timeout):
                await websocket.close(code=status.WS_1011_INTERNAL_ERROR)

    def _leave_scope(self, connection: Connection) -> ScopeChange:
        """Take a socket out of the scope it was reading, and of its channels."""
        scope_id = connection.scope_id

        for channel in list(connection.channels):
            self._forget_channel(connection, channel)

        connection.channels.clear()

        if scope_id is None:
            return ScopeChange()

        holders = self._by_scope.get(scope_id)

        if holders is None:
            return ScopeChange()

        holders.discard(connection)

        if holders:
            return ScopeChange()

        del self._by_scope[scope_id]

        return ScopeChange(removed=scope_id)

    def _forget_channel(self, connection: Connection, channel: str) -> None:
        if connection.scope_id is None:
            return

        key = (connection.scope_id, channel)
        subscribers = self._by_channel.get(key)

        if subscribers is None:
            return

        subscribers.discard(connection)

        if not subscribers:
            del self._by_channel[key]


__all__ = [
    "Connection",
    "ScopeChange",
    "WebSocketManager",
]
