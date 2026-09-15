# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import json
import logging
import socket
from collections.abc import Collection, Iterable
from datetime import date, time
from typing import Any

from fastedgy.bus import Bus
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.metadata_model.generator import generate_metadata_name
from fastedgy.orm import Database
from fastedgy.realtime.auth import RealtimeAuth
from fastedgy.realtime.events import OnRealtimeDeliveredEvent
from fastedgy.realtime.manager import WebSocketManager

logger = logging.getLogger("fastedgy.realtime.broadcaster")

# Postgres refuses a NOTIFY payload of 8000 bytes or more. The margin covers the
# encoding of what is added around the data.
MAX_PAYLOAD = 7000

MAX_USERS_PER_NOTIFY = 200


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

    async def ensure_listening(self, timeout: float = 5.0) -> bool:
        await self.start()

        return await self.wait_listening(timeout)

    async def start(self) -> None:
        """Start listening, unless this process already does."""
        if self._listener_task is not None:
            return

        self._shutdown.clear()
        self._consumer_tasks = [
            asyncio.create_task(self._consume_notifications()) for _ in range(self._consumer_pool_size)
        ]
        self._listener_task = asyncio.create_task(self._listen())
        self._supervisor_task = asyncio.create_task(self._supervise())
        logger.info("WebSocket broadcaster started")

    async def stop(self) -> None:
        """Stop the listener, the supervisor and the consumers."""
        if self._listener_task is None and self._supervisor_task is None and not self._consumer_tasks:
            return

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

    def scope_channel(self, scope_id: int) -> str:
        """The PG channel a scope's events travel on."""
        return f"{self._channel}_{scope_id}"

    async def follow(self, scope_id: int | None) -> None:
        """Start hearing what is published to a scope.

        Called when this process takes its first socket for one. A worker is
        woken for the scopes it serves and for no other, which is what keeps an
        event from costing something on every worker of the fleet.
        """
        if scope_id is None:
            return

        channel = self.scope_channel(scope_id)

        if channel in self._followed:
            return

        self._followed.add(channel)

        if self._pg_conn is not None:
            await self._add_listener(self._pg_conn, channel)

    async def unfollow(self, scope_id: int | None) -> None:
        """Stop hearing a scope this process no longer holds a socket for."""
        if scope_id is None:
            return

        channel = self.scope_channel(scope_id)

        if channel not in self._followed:
            return

        self._followed.discard(channel)

        if self._pg_conn is not None:
            await self._remove_listener(self._pg_conn, channel)

    async def broadcast_to_scope(
        self,
        scope_id: int,
        event_type: str,
        data: Any,
        channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        exclude_user_ids: Collection[int] | None = None,
        about: tuple[type | str, Any] | None = None,
        audience: Collection[int] | None = None,
    ) -> None:
        """Announce something to a scope, on the workers that serve it.

        With [channels], only to the sockets subscribed to one of them. [meta]
        is what is known about the write rather than about the record, and rides
        beside the event on every frame. [exclude_user_ids] leaves the sockets of
        these accounts out, the author of the event among them.

        [about] names the record the event is about, as a model (its class or its
        name) and an id: a worker then asks `RealtimeAuth.audience` who of its
        sockets may hear it, and a guarded model's rules answer. [audience] is who
        may hear it when that is known before it goes out, the readers of a record
        about to be deleted for one: nobody else is asked, or told.
        """
        payload: dict[str, Any] = {
            "target": "scope",
            "scope_id": scope_id,
            "event_type": event_type,
            "data": data,
            "channels": channels,
            "meta": meta or {},
        }

        if exclude_user_ids:
            payload["exclude"] = sorted(exclude_user_ids)

        if about is not None:
            name = about[0] if isinstance(about[0], str) else generate_metadata_name(about[0])
            payload["about"] = {"model": name, "id": about[1]}

        if audience is None:
            await self._publish(payload, self.scope_channel(scope_id))

            return

        ids = sorted(set(audience))

        for start in range(0, len(ids), MAX_USERS_PER_NOTIFY):
            await self._publish(
                {**payload, "only": ids[start : start + MAX_USERS_PER_NOTIFY]}, self.scope_channel(scope_id)
            )

    async def broadcast_record(
        self,
        scope_id: int,
        model: str,
        record_id: int,
        action: str,
        extra: dict[str, Any] | None = None,
        related_channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        audience: Collection[int] | None = None,
    ) -> None:
        """Announce a write on one record, to whoever asked about it.

        Three kinds of channel carry it: the model, for a list that has to
        refresh; the record itself, for whoever is reading that one; and the
        records it hangs off, so a page reading a fragment hears about an
        attachment written into it. [extra] is what the model declared to carry
        alongside the identifiers.

        [audience] is who may hear it, when that is known before it goes out: the
        members found able to read a record of a guarded model before it was
        deleted. Without, a worker asks who of its sockets can read the record.
        """
        await self.broadcast_to_scope(
            scope_id,
            f"{model}.{action}",
            {"model": model, "id": record_id, **(extra or {})},
            channels=[model, f"{model}:{record_id}", *(related_channels or [])],
            meta=meta,
            about=(model, record_id),
            audience=audience,
        )

    async def broadcast_to_users(
        self,
        user_ids: Iterable[int],
        event_type: str,
        data: Any,
        channels: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        ids = sorted(set(user_ids))

        for start in range(0, len(ids), MAX_USERS_PER_NOTIFY):
            await self._publish(
                {
                    "target": "users",
                    "user_ids": ids[start : start + MAX_USERS_PER_NOTIFY],
                    "event_type": event_type,
                    "data": data,
                    "channels": channels,
                    "meta": meta or {},
                }
            )

    async def broadcast_to_user(
        self,
        user_id: int,
        event_type: str,
        data: Any,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Announce something to one account, wherever it is connected."""
        await self.broadcast_to_users([user_id], event_type, data, meta=meta)

    async def recheck_users(self, user_ids: Iterable[int]) -> None:
        """Have the sockets of these accounts, on every worker, check again what
        they were let in with now rather than at their next round."""
        ids = sorted(set(user_ids))

        for start in range(0, len(ids), MAX_USERS_PER_NOTIFY):
            await self._notify(json.dumps({"target": "recheck", "user_ids": ids[start : start + MAX_USERS_PER_NOTIFY]}))

    async def _publish(self, payload: dict[str, Any], channel: str | None = None) -> None:
        """Publish, shedding what it must to stay under what NOTIFY accepts.

        Postgres refuses a payload of 8000 bytes outright, and the event would
        be lost for everyone. So it goes out with less rather than not at all:
        first without its data but for the model and the id that name a record,
        marked as such, which tells the client to read the record for itself;
        then, if that is still too much, without the channels that narrow it,
        which serves the whole scope instead of exactly the sockets that asked.
        Over-telling beats a silence nothing recovers from.
        """
        channel = channel or self._channel
        raw = json.dumps(payload, default=_encode)

        if len(raw.encode()) <= MAX_PAYLOAD:
            await self._notify(raw, channel)

            return

        logger.info("Broadcast payload over %d bytes, sent without its data (%s)", MAX_PAYLOAD, payload["event_type"])
        payload = {
            **payload,
            "data": _identity(payload.get("data")),
            "meta": {**payload.get("meta", {}), "truncated": True},
        }
        raw = json.dumps(payload, default=_encode)

        if len(raw.encode()) > MAX_PAYLOAD:
            logger.warning(
                "Broadcast payload still over %d bytes, sent to the whole scope (%s)",
                MAX_PAYLOAD,
                payload["event_type"],
            )
            raw = json.dumps({**payload, "channels": None}, default=_encode)

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

        if target == "recheck":
            self._manager.recheck(payload.get("user_ids") or [])

            return

        event_type = payload["event_type"]
        data = payload.get("data")
        channels = payload.get("channels")
        meta = payload.get("meta") or None

        if target == "scope":
            scope_id = payload["scope_id"]
            exclude = payload.get("exclude")
            only = payload.get("only")

            if only is None:
                only = await self._audience(scope_id, event_type, data, channels, exclude, payload.get("about"))

            delivered = await self._manager.deliver_to_scope(scope_id, event_type, data, channels, meta, exclude, only)
        elif target == "users":
            delivered = await self._manager.deliver_to_users(payload["user_ids"], event_type, data, meta)
        elif target == "user":
            delivered = await self._manager.deliver_to_user(payload["user_id"], event_type, data, meta)
        else:
            return

        await self._report(event_type, data, channels, delivered)

    async def _audience(
        self,
        scope_id: int,
        event_type: str,
        data: Any,
        channels: list[str] | None,
        exclude: Any,
        about: Any,
    ) -> Collection[int] | None:
        """Who of the accounts this process would deliver an event to may hear it,
        as the application's `RealtimeAuth` says; None when nobody here would."""
        holders = self._manager.holders(scope_id, channels, exclude)

        if not holders:
            return None

        auth = get_service(RealtimeAuth)

        if about is None:
            return await auth.audience(scope_id, event_type, data, holders)

        model_cls = await _model_named(about.get("model")) if isinstance(about, dict) else None

        if model_cls is None or about.get("id") is None:
            logger.warning("Broadcast about a record it does not name, delivered to nobody (%s)", event_type)

            return set()

        return await auth.audience(scope_id, event_type, data, holders, (model_cls, about["id"]))

    async def _report(self, event_type: str, data: Any, channels: list[str] | None, delivered: set[int]) -> None:
        if not channels or not delivered:
            return

        bus = get_service(Bus)

        if not bus.has_listeners(OnRealtimeDeliveredEvent):
            return

        watchers = self._manager.watchers(delivered, channels)

        if watchers:
            await bus.dispatch(OnRealtimeDeliveredEvent(event_type, data, watchers))

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
        """Listen to exactly the scopes this process holds a socket for.

        The endpoint says so as sockets come and go, and this is what heals a
        drift: a follow that happened while the connection was down, a socket
        dropped from under a delivery. A worker deaf to a scope it serves would
        say nothing about it, which is the failure nobody would notice.
        """
        held = {self.scope_channel(scope_id) for scope_id in self._manager.scopes()}
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
            logger.info("Listening on PG channel '%s' and %d scopes", self._channel, len(self._followed))

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


async def _model_named(name: Any) -> type | None:
    if not isinstance(name, str):
        return None

    from fastedgy.metadata_model.registry import MetadataModelRegistry
    from fastedgy.realtime.model import registry

    return registry.model_class(name) or await get_service(MetadataModelRegistry).get_model_from_name(name)


def _encode(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date | time) else str(value)


def _identity(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    return {key: data[key] for key in ("model", "id") if key in data} or None


__all__ = [
    "MAX_PAYLOAD",
    "MAX_USERS_PER_NOTIFY",
    "WebSocketBroadcaster",
]
