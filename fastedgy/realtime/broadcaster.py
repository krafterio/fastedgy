# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import json
import logging
import socket
from typing import Any

from fastedgy.config import BaseSettings
from fastedgy.orm import Database
from fastedgy.realtime.manager import WebSocketManager

logger = logging.getLogger("fastedgy.realtime.broadcaster")

# Postgres refuses a NOTIFY payload of 8000 bytes or more. The margin covers the
# encoding of what is added around the data.
MAX_PAYLOAD = 7000


class WebSocketBroadcaster:
    """Reaches the sockets of every worker, through PostgreSQL NOTIFY/LISTEN.

    A socket is held by one process, and an event is raised in whichever process
    served the request: without this, an agent writing through one worker is
    invisible to a browser connected to another. Each worker holds a LISTEN
    connection, and every published event comes back to all of them, which then
    deliver to their own sockets.

    Everything it is tuned by comes from the settings, under `realtime_`, so a
    deployment whose network evicts an idle flow sooner than the default assumes
    says so in its own `.env` rather than in a subclass.
    """

    def __init__(self, settings: BaseSettings, db: Database, manager: WebSocketManager) -> None:
        self._db = db
        self._manager = manager
        self._channel = settings.realtime_channel
        self._consumer_pool_size = settings.realtime_consumer_pool_size
        self._heartbeat_interval = settings.realtime_heartbeat_interval
        self._heartbeat_timeout = settings.realtime_heartbeat_timeout
        self._reconnect_backoff_start = settings.realtime_reconnect_backoff_start
        self._reconnect_backoff_max = settings.realtime_reconnect_backoff_max
        self._supervise_interval = settings.realtime_supervise_interval
        self._tcp_keepidle = settings.realtime_tcp_keepidle
        self._tcp_keepintvl = settings.realtime_tcp_keepintvl
        self._tcp_keepcnt = settings.realtime_tcp_keepcnt
        self._followed: set[str] = set()
        self._pg_conn: Any = None
        self._listener_task: asyncio.Task | None = None
        self._supervisor_task: asyncio.Task | None = None
        self._consumer_tasks: list[asyncio.Task] = []
        self._shutdown = asyncio.Event()
        # Set while a LISTEN connection is established: what says whether this
        # worker is actually reachable by a broadcast.
        self._listening = asyncio.Event()
        # asyncpg calls the notify callback synchronously, so it cannot await a
        # delivery: it only enqueues, and a bounded pool of long-lived consumers
        # drains the queue. A task spawned per NOTIFY would be held by the loop
        # through a weak reference alone, and could be collected mid-flight
        # while holding a pooled connection.
        self._notify_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=settings.realtime_notify_queue_size)

    @property
    def is_listening(self) -> bool:
        """Whether a LISTEN connection is established right now."""
        return self._listening.is_set()

    async def wait_listening(self, timeout: float = 5.0) -> bool:
        """Wait for the LISTEN connection, for a caller that cannot miss an event."""
        try:
            await asyncio.wait_for(self._listening.wait(), timeout=timeout)
        except TimeoutError:
            return False

        return True

    async def start(self) -> None:
        """Start listening. Called from the application lifespan."""
        self._shutdown.clear()
        self._consumer_tasks = [
            asyncio.create_task(self._consume_notifications()) for _ in range(self._consumer_pool_size)
        ]
        self._listener_task = asyncio.create_task(self._listen())
        self._supervisor_task = asyncio.create_task(self._supervise())
        logger.info("WebSocket broadcaster started")

    async def stop(self) -> None:
        """Stop the listener, the supervisor and the consumers."""
        self._shutdown.set()
        tasks = [self._supervisor_task, self._listener_task, *self._consumer_tasks]

        for task in tasks:
            if task:
                task.cancel()

        for task in tasks:
            if task:
                try:
                    await task
                except (asyncio.CancelledError, Exception) as e:  # noqa: BLE001 - a task being stopped answers for nothing
                    logger.debug("Broadcaster task stopped with %r", e)

        self._supervisor_task = None
        self._listener_task = None
        self._consumer_tasks = []
        logger.info("WebSocket broadcaster stopped")

    def workspace_channel(self, workspace_id: int) -> str:
        """The PG channel a workspace's events travel on."""
        return f"{self._channel}_{workspace_id}"

    async def follow(self, workspace_id: int | None) -> None:
        """Start hearing what is published to a workspace.

        Called when this process takes its first socket for one. A worker is
        woken for the workspaces it serves and for no other, which is what keeps
        an event from costing something on every worker of the fleet.
        """
        if workspace_id is None:
            return

        channel = self.workspace_channel(workspace_id)

        if channel in self._followed:
            return

        self._followed.add(channel)

        if self._pg_conn is not None:
            await self._add_listener(self._pg_conn, channel)

    async def unfollow(self, workspace_id: int | None) -> None:
        """Stop hearing a workspace this process no longer holds a socket for."""
        if workspace_id is None:
            return

        channel = self.workspace_channel(workspace_id)

        if channel not in self._followed:
            return

        self._followed.discard(channel)

        if self._pg_conn is not None:
            await self._remove_listener(self._pg_conn, channel)

    async def broadcast_to_workspace(
        self,
        workspace_id: int,
        event_type: str,
        data: Any,
        channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Announce something to a workspace, on the workers that serve it.

        With [channels], only to the sockets subscribed to one of them. [meta]
        is what is known about the write rather than about the record, and rides
        beside the event on every frame.
        """
        await self._publish(
            {
                "target": "workspace",
                "workspace_id": workspace_id,
                "event_type": event_type,
                "data": data,
                "channels": channels,
                "meta": meta or {},
            },
            self.workspace_channel(workspace_id),
        )

    async def broadcast_record(
        self,
        workspace_id: int,
        model: str,
        record_id: int,
        action: str,
        extra: dict[str, Any] | None = None,
        related_channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Announce a write on one record, to whoever asked about it.

        Three kinds of channel carry it: the model, for a list that has to
        refresh; the record itself, for whoever is reading that one; and the
        records it hangs off, so a page reading a fragment hears about an
        attachment written into it. [extra] is what the model declared to carry
        alongside the identifiers.
        """
        await self.broadcast_to_workspace(
            workspace_id,
            f"{model}.{action}",
            {"model": model, "id": record_id, **(extra or {})},
            channels=[model, f"{model}:{record_id}", *(related_channels or [])],
            meta=meta,
        )

    async def broadcast_to_user(
        self,
        user_id: int,
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Announce something to one account, wherever it is connected."""
        await self._publish(
            {
                "target": "user",
                "user_id": user_id,
                "event_type": event_type,
                "data": data,
                "meta": meta or {},
            }
        )

    async def _publish(self, payload: dict[str, Any], channel: str | None = None) -> None:
        """Publish, shedding what it must to stay under what NOTIFY accepts.

        Postgres refuses a payload of 8000 bytes outright, and the event would
        be lost for everyone. So it goes out with less rather than not at all:
        first without its data, marked as such, which tells the client to read
        the record for itself; then, if that is still too much, without the
        channels that narrow it, which serves the whole workspace instead of
        exactly the sockets that asked. Over-telling beats a silence nothing
        recovers from.
        """
        channel = channel or self._channel
        raw = json.dumps(payload, default=str)

        if len(raw.encode()) <= MAX_PAYLOAD:
            await self._notify(raw, channel)

            return

        logger.info("Broadcast payload over %d bytes, sent without its data (%s)", MAX_PAYLOAD, payload["event_type"])
        payload = {**payload, "data": None, "meta": {**payload.get("meta", {}), "truncated": True}}
        raw = json.dumps(payload, default=str)

        if len(raw.encode()) > MAX_PAYLOAD:
            logger.warning(
                "Broadcast payload still over %d bytes, sent to the whole workspace (%s)",
                MAX_PAYLOAD,
                payload["event_type"],
            )
            raw = json.dumps({**payload, "channels": None}, default=str)

        await self._notify(raw, channel)

    async def _notify(self, payload: str, channel: str | None = None) -> None:
        from sqlalchemy import text

        await self._db.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": channel or self._channel, "payload": payload},
        )

    async def _consume_notifications(self) -> None:
        """Drain the queue, one payload at a time."""
        while not self._shutdown.is_set():
            payload = await self._notify_queue.get()

            try:
                await self._handle_notify(payload)
            except Exception as e:  # noqa: BLE001 - one bad payload must not take the consumer down
                logger.error("Error handling NOTIFY payload: %s", e)
            finally:
                self._notify_queue.task_done()

    async def _handle_notify(self, raw_payload: str) -> None:
        """Deliver what was published to the sockets this process holds."""
        # Most workers hold nothing for most events: nothing is parsed, nothing
        # is read, nothing is looked up.
        if self._manager.is_idle:
            return

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning("Invalid NOTIFY payload: %s", raw_payload[:200])

            return

        target = payload.get("target")
        event_type = payload["event_type"]
        data = payload.get("data")
        meta = payload.get("meta") or None

        if target == "workspace":
            await self._manager.deliver_to_workspace(
                payload["workspace_id"],
                event_type,
                data,
                payload.get("channels"),
                meta,
            )
        elif target == "user":
            await self._manager.deliver_to_user(payload["user_id"], event_type, data, meta)

    async def _supervise(self) -> None:
        """Restart the listener, or any consumer, that dies on its own."""
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=self._supervise_interval)
                break
            except TimeoutError:
                pass

            if self._shutdown.is_set():
                break

            if self._listener_task is None or self._listener_task.done():
                logger.error("Listener task is dead, restarting it")
                self._listener_task = asyncio.create_task(self._listen())

            for index, task in enumerate(self._consumer_tasks):
                if task.done():
                    logger.error("Consumer task %d is dead, restarting it", index)
                    self._consumer_tasks[index] = asyncio.create_task(self._consume_notifications())

            await self._reconcile_followed()

    async def _reconcile_followed(self) -> None:
        """Listen to exactly the workspaces this process holds a socket for.

        The endpoint says so as sockets come and go, and this is what heals a
        drift: a follow that happened while the connection was down, a socket
        dropped from under a delivery. A worker deaf to a workspace it serves
        would say nothing about it, which is the failure nobody would notice.
        """
        held = {self.workspace_channel(workspace_id) for workspace_id in self._manager.workspaces()}
        stale = self._followed - held

        for channel in stale:
            self._followed.discard(channel)

            if self._pg_conn is not None:
                await self._remove_listener(self._pg_conn, channel)

        for channel in held - self._followed:
            self._followed.add(channel)

            if self._pg_conn is not None:
                await self._add_listener(self._pg_conn, channel)

    async def _listen(self) -> None:
        """Hold a LISTEN connection, re-establishing it whenever it drops."""
        backoff = self._reconnect_backoff_start
        failures = 0

        while not self._shutdown.is_set():
            try:
                await self._listen_once()
                backoff = self._reconnect_backoff_start
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - whatever broke the connection, the answer is to re-establish it
                if self._shutdown.is_set():
                    break

                from fastedgy.dependencies import get_service
                from fastedgy.health import Health

                failures += 1

                # A blip that heals in a couple of attempts (a deploy
                # switchover, a database failover) is expected. Past that, the
                # level follows the divergence rather than the count: if the
                # database itself is unreachable, this is the outage every
                # request is already reporting, so a warning; if the database
                # answers while our own connection cannot come back, that is
                # the pathology this supervisor exists for.
                if failures < 3 or get_service(Health).is_shutting_down or not await self._database_reachable():
                    logger.warning(
                        "Broadcaster listener connection lost (%s); reconnecting in %.0fs (attempt %d)",
                        e,
                        backoff,
                        failures,
                    )
                else:
                    logger.error(
                        "Broadcaster listener still down after %d attempts while the database answers (%s); "
                        "reconnecting in %.0fs",
                        failures,
                        e,
                        backoff,
                    )

                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=backoff)
                except TimeoutError:
                    pass

                backoff = min(backoff * 2, self._reconnect_backoff_max)

    async def _listen_once(self) -> None:
        """Open one LISTEN connection and hold it, probing until it dies."""
        conn_ctx = self._db.connection()

        async with conn_ctx:
            raw_conn = await conn_ctx.get_raw_connection()
            pg_conn = self._unwrap_asyncpg(raw_conn)

            if pg_conn is None:
                raise RuntimeError("Cannot access underlying asyncpg connection for LISTEN")

            self._enable_keepalive(pg_conn)
            await self._add_listener(pg_conn, self._channel)

            # A new connection is listening to nothing: what this worker still
            # serves is said again on it.
            for channel in list(self._followed):
                await self._add_listener(pg_conn, channel)

            self._pg_conn = pg_conn
            self._listening.set()
            logger.info("Listening on PG channel '%s' and %d workspaces", self._channel, len(self._followed))

            try:
                while not self._shutdown.is_set():
                    try:
                        await asyncio.wait_for(self._shutdown.wait(), timeout=self._heartbeat_interval)
                        break
                    except TimeoutError:
                        pass

                    # Through the connection context rather than the raw
                    # asyncpg one, so a dead connection is invalidated by the
                    # pool instead of being handed out again.
                    await asyncio.wait_for(conn_ctx.execute("SELECT 1"), timeout=self._heartbeat_timeout)
            finally:
                self._listening.clear()
                self._pg_conn = None
                await self._remove_listener(pg_conn, self._channel)

                for channel in list(self._followed):
                    await self._remove_listener(pg_conn, channel)

    async def _database_reachable(self) -> bool:
        """Probe the database through the managed pool.

        Through the pool, never through an ad-hoc raw connection: a failing one
        poisons the pool it came from.
        """
        from sqlalchemy import text

        try:
            async with asyncio.timeout(5):
                await self._db.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - anything at all means unreachable
            return False

        return True

    def _on_notify(self, connection: Any, pid: Any, channel: Any, payload: str) -> None:
        # Synchronous callback: enqueue, and never block or await here.
        try:
            self._notify_queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("NOTIFY queue full, dropping a broadcast payload")

    async def _add_listener(self, pg_conn: Any, channel: str) -> None:
        import inspect

        add_listener = getattr(pg_conn, "add_listener", None)

        if add_listener is None:
            raise RuntimeError("Connection missing add_listener")

        if inspect.iscoroutinefunction(add_listener):
            await add_listener(channel, self._on_notify)
        else:
            add_listener(channel, self._on_notify)

    async def _remove_listener(self, pg_conn: Any, channel: str) -> None:
        import inspect

        try:
            remove_listener = getattr(pg_conn, "remove_listener", None)

            if remove_listener:
                if inspect.iscoroutinefunction(remove_listener):
                    await remove_listener(channel, self._on_notify)
                else:
                    remove_listener(channel, self._on_notify)
        except Exception as e:  # noqa: BLE001 - the connection is being dropped anyway
            logger.debug("Cannot remove the notify listener of '%s': %s", channel, e)

    def _enable_keepalive(self, pg_conn: Any) -> None:
        transport = getattr(pg_conn, "_transport", None)
        sock = transport.get_extra_info("socket") if transport is not None else None

        if sock is None:
            return

        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

            for name, value in (
                ("TCP_KEEPIDLE", self._tcp_keepidle),
                ("TCP_KEEPINTVL", self._tcp_keepintvl),
                ("TCP_KEEPCNT", self._tcp_keepcnt),
            ):
                option = getattr(socket, name, None)

                if option is not None:
                    sock.setsockopt(socket.IPPROTO_TCP, option, value)
        except OSError as e:
            logger.debug("Could not set TCP keepalive on the LISTEN socket: %s", e)

    @staticmethod
    def _unwrap_asyncpg(conn: Any) -> Any:
        """The raw asyncpg connection under the SQLAlchemy adapters."""
        for attr in ("driver_connection", "dbapi_connection", "connection"):
            inner = getattr(conn, attr, None)

            if inner is not None and hasattr(inner, "add_listener"):
                return inner

        if hasattr(conn, "add_listener"):
            return conn

        return None


__all__ = [
    "MAX_PAYLOAD",
    "WebSocketBroadcaster",
]
