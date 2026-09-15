# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from fastedgy.bus import BaseEvent, Bus
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject, get_service
from fastedgy.realtime.auth import RealtimeAuth
from fastedgy.realtime.broadcaster import WebSocketBroadcaster
from fastedgy.realtime.events import OnRealtimeDisconnectEvent, OnRealtimeFrameEvent
from fastedgy.realtime.manager import Connection, ScopeChange, WebSocketManager
from fastedgy.realtime.model import registry as realtime_registry

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.realtime.auth import Scope

router = APIRouter()
logger = logging.getLogger("fastedgy.realtime.api")

# Seconds [BaseSettings.realtime_frame_limit] counts the frames of a socket over.
FRAME_WINDOW = 10.0


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    settings: BaseSettings = Inject(BaseSettings),
    manager: WebSocketManager = Inject(WebSocketManager),
    broadcaster: WebSocketBroadcaster = Inject(WebSocketBroadcaster),
    auth: RealtimeAuth = Inject(RealtimeAuth),
) -> None:
    """What one client writes reaches the browsers watching that scope.

    Reads are what the rest of the API is for: this carries announcements, and
    hands a frame of the application's own to the bus.
    """
    await websocket.accept()

    authenticated = await _authenticate(websocket, settings, auth)

    if authenticated is None:
        return

    user, scope, token, asked = authenticated

    if user.id is None:
        return

    if manager.count(user.id) >= settings.realtime_max_sockets_per_user:
        await _refuse(websocket, "Too many connections")

        return

    await broadcaster.ensure_listening()

    try:
        await websocket.send_json(
            {
                "type": "auth_success",
                "data": {
                    "user_id": user.id,
                    "scope": scope.slug if scope else None,
                },
            }
        )
    except Exception as e:  # noqa: BLE001 - the client left before hearing it was accepted
        logger.debug("WebSocket gone before its authentication was answered: %s", e)

        return

    connection = manager.connect(user.id, websocket)
    connection.asked_scope = asked
    # What resolves the scope of a socket, a `watch` of its client or a check of
    # its membership, does it one at a time: an older answer applied after a
    # newer one would put the socket back where it no longer belongs.
    lock = asyncio.Lock()
    recheck: asyncio.Task | None = None

    try:
        await _apply(broadcaster, manager.watch(connection, scope.id if scope else None))
        recheck = asyncio.create_task(
            _recheck(websocket, connection, token, lock, manager, broadcaster, auth, settings.realtime_recheck_interval)
        )
        await _listen(websocket, connection, user, lock, manager, broadcaster, auth, settings)
    finally:
        if recheck is not None:
            recheck.cancel()

        await _apply(broadcaster, manager.disconnect(connection))
        await _dispatch(OnRealtimeDisconnectEvent(connection, user))


async def _authenticate(
    websocket: WebSocket,
    settings: BaseSettings,
    auth: RealtimeAuth,
) -> "tuple[User, Scope | None, str, Any] | None":
    """Read the first frame, and answer whether the socket may stay.

    A browser cannot set headers on a WebSocket, so the bearer arrives as the
    first frame, and an unauthenticated socket is held open until it does or
    until the timeout runs out. Besides the account and its scope, it answers
    with what the socket is checked again against for as long as it lives: the
    bearer, and the scope as the client named it.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=settings.realtime_auth_timeout)
    except TimeoutError, WebSocketDisconnect:
        await _refuse(websocket, "Authentication timeout")

        return None
    except Exception as e:  # noqa: BLE001 - a binary frame, or anything else than text
        logger.debug("Unreadable authentication frame: %s", e)
        await _refuse(websocket, "Invalid authentication format")

        return None

    message = _parse(raw) if len(raw) <= settings.realtime_max_frame_size else None

    if not isinstance(message, dict):
        await _refuse(websocket, "Invalid authentication format")

        return None

    data = _data(message)
    token = data.get("token")

    if message.get("type") != "authenticate" or not isinstance(token, str) or not token:
        await _refuse(websocket, "Invalid authentication message")

        return None

    user = await auth.user_of_token(token)

    if user is None:
        await _refuse(websocket, "Invalid authentication token")

        return None

    asked = _scope(data)
    scope = await auth.scope_of(user, asked)

    if asked and scope is None:
        await _refuse(websocket, "Scope not found")

        return None

    return user, scope, token, asked


async def _listen(
    websocket: WebSocket,
    connection: Connection,
    user: "User",
    lock: asyncio.Lock,
    manager: WebSocketManager,
    broadcaster: WebSocketBroadcaster,
    auth: RealtimeAuth,
    settings: BaseSettings,
) -> None:
    """Take what the client says about itself, and hand on the rest.

    `watch` says which scope this tab is reading, `subscribe` and `unsubscribe`
    say which records of it to hear about. A client sending more frames than
    [BaseSettings.realtime_frame_limit] in [FRAME_WINDOW] seconds, or a frame
    heavier than [BaseSettings.realtime_max_frame_size], loses its socket.
    """
    loop = asyncio.get_running_loop()
    window = loop.time()
    received = 0

    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        except Exception as e:  # noqa: BLE001 - a client sending nonsense loses its socket, not the worker
            logger.debug("Error reading a WebSocket frame: %s", e)

            return

        now = loop.time()

        if now - window >= FRAME_WINDOW:
            window, received = now, 0

        received += 1

        if received > settings.realtime_frame_limit:
            logger.debug("Closing a socket of user %s sending too many frames", connection.user_id)
            await _close(websocket, status.WS_1008_POLICY_VIOLATION)

            return

        if len(raw) > settings.realtime_max_frame_size:
            logger.debug("Closing a socket of user %s sending a frame too heavy", connection.user_id)
            await _close(websocket, status.WS_1009_MESSAGE_TOO_BIG)

            return

        message = _parse(raw)

        if not isinstance(message, dict):
            return

        event_type = message.get("type")
        data = _data(message)

        if event_type == "heartbeat":
            continue

        if event_type == "watch":
            asked = _scope(data)

            # The scope already read costs nothing: a membership it lost is the
            # periodic check's to find.
            if asked == connection.asked_scope:
                continue

            async with lock:
                connection.asked_scope = asked
                scope = await auth.scope_of(user, asked)
                await _apply(broadcaster, manager.watch(connection, scope.id if scope else None))
        elif event_type == "subscribe":
            manager.subscribe(connection, _channels(data))
        elif event_type == "unsubscribe":
            manager.unsubscribe(connection, _channels(data))
        elif isinstance(event_type, str) and event_type:
            await _dispatch(OnRealtimeFrameEvent(connection, user, event_type, data))


async def _recheck(
    websocket: WebSocket,
    connection: Connection,
    token: str,
    lock: asyncio.Lock,
    manager: WebSocketManager,
    broadcaster: WebSocketBroadcaster,
    auth: RealtimeAuth,
    interval: float,
) -> None:
    """Check again, for as long as the socket lives, what it was let in with.

    A bearer expires or is revoked, an account goes, a membership ends: none of
    it reaches a socket already open. The bearer is resolved again, and a socket
    it no longer stands for is refused, which has the client authenticate again
    with what it holds now. The scope the client named is resolved again, and one
    the account lost is left, the socket staying for what is addressed to the
    account itself. Every [interval] seconds, and at once when
    [Connection.recheck] is set.
    """
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(connection.recheck.wait(), timeout=interval)

        connection.recheck.clear()

        try:
            user = await auth.user_of_token(token)

            if user is None or user.id != connection.user_id:
                await _refuse(websocket, "Invalid authentication token")

                return

            async with lock:
                scope = await auth.scope_of(user, connection.asked_scope)
                await _apply(broadcaster, manager.watch(connection, scope.id if scope else None))
        except Exception as e:  # noqa: BLE001 - checked again at the next round
            logger.debug("Could not check a socket of user %s again: %s", connection.user_id, e)


async def _apply(broadcaster: WebSocketBroadcaster, change: ScopeChange) -> None:
    """Follow what this process now serves, and let go of what it does not.

    A worker is woken for the scopes it holds a socket for, and for no other:
    that is what keeps one event from costing something on every worker.
    """
    if change.added is None and change.removed is None:
        return

    await broadcaster.follow(change.added)
    await broadcaster.unfollow(change.removed)


async def _dispatch(event: BaseEvent) -> None:
    bus = get_service(Bus)

    if bus.has_listeners(type(event)):
        await bus.dispatch(event)


def _parse(raw: str) -> Any:
    """A frame read as JSON, or None when it is not JSON at all."""
    try:
        return json.loads(raw)
    except ValueError, RecursionError:
        return None


def _data(message: dict[str, Any]) -> dict[str, Any]:
    """What a frame carries, read as nothing when it is not an object.

    A frame is the client's to write: a payload of another shape must not end in
    an exception the client chose to raise.
    """
    data = message.get("data")

    return data if isinstance(data, dict) else {}


def _scope(data: dict[str, Any]) -> Any:
    """What a frame says this socket is reading.

    The protocol names it `scope`, and the application decides what a scope is.
    """
    return data.get("scope")


def _channels(data: dict[str, Any]) -> list[str]:
    """The channels a frame names: `engram` for a list, `engram:42` for a record.

    Only channels of a registered model are kept: a client cannot invent one and
    make itself heard on it.
    """
    asked = data.get("channels")

    if not isinstance(asked, list) or not asked:
        asked = [data["channel"]] if isinstance(data.get("channel"), str) else []

    known = set(realtime_registry.models())
    channels = []

    for channel in asked:
        if not isinstance(channel, str):
            continue

        if channel.split(":", 1)[0] in known:
            channels.append(channel)

    return channels


async def _refuse(websocket: WebSocket, reason: str) -> None:
    logger.debug("WebSocket refused: %s", reason)

    with contextlib.suppress(Exception):
        await websocket.send_json({"type": "auth_error", "data": {"message": reason}})

    await _close(websocket, status.WS_1008_POLICY_VIOLATION)


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception as e:  # noqa: BLE001 - the socket may already be gone
        logger.debug("Cannot close the socket: %s", e)


__all__ = [
    "router",
    "websocket_endpoint",
]
