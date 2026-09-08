# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject
from fastedgy.realtime.auth import user_of_token, workspace_of
from fastedgy.realtime.broadcaster import WebSocketBroadcaster
from fastedgy.realtime.manager import Connection, WebSocketManager, WorkspaceChange
from fastedgy.realtime.model import registry as realtime_registry

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace

router = APIRouter()
logger = logging.getLogger("fastedgy.realtime.api")


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    settings: BaseSettings = Inject(BaseSettings),
    manager: WebSocketManager = Inject(WebSocketManager),
    broadcaster: WebSocketBroadcaster = Inject(WebSocketBroadcaster),
) -> None:
    """What one client writes reaches the browsers watching that workspace.

    Reads are what the rest of the API is for: this carries announcements, and
    nothing that arrives here changes anything in the database.
    """
    await websocket.accept()

    authenticated = await _authenticate(websocket, settings.realtime_auth_timeout)

    if authenticated is None:
        return

    user, workspace = authenticated

    if user.id is None:
        return

    connection = manager.connect(user.id, websocket)
    await _apply(broadcaster, manager.watch(connection, workspace.id if workspace else None))

    try:
        await _listen(websocket, connection, user, manager, broadcaster)
    finally:
        await _apply(broadcaster, manager.disconnect(connection))


async def _authenticate(websocket: WebSocket, timeout: float) -> "tuple[User, Workspace | None] | None":
    """Read the first frame, and answer whether the socket may stay.

    A browser cannot set headers on a WebSocket, so the bearer arrives as the
    first frame, and an unauthenticated socket is held open until it does or
    until [timeout] runs out.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
    except TimeoutError, WebSocketDisconnect:
        await _refuse(websocket, "Authentication timeout")

        return None

    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        await _refuse(websocket, "Invalid authentication format")

        return None

    data = message.get("data") or {}

    if message.get("type") != "authenticate" or not data.get("token"):
        await _refuse(websocket, "Invalid authentication message")

        return None

    user = await user_of_token(data["token"])

    if user is None:
        await _refuse(websocket, "Invalid authentication token")

        return None

    workspace = await workspace_of(user, data.get("workspace"))

    if data.get("workspace") and workspace is None:
        await _refuse(websocket, "Workspace not found")

        return None

    await websocket.send_json(
        {
            "type": "auth_success",
            "data": {
                "user_id": user.id,
                "workspace": workspace.slug if workspace else None,
            },
        }
    )

    return user, workspace


async def _listen(
    websocket: WebSocket,
    connection: Connection,
    user: "User",
    manager: WebSocketManager,
    broadcaster: WebSocketBroadcaster,
) -> None:
    """Take what the client says about itself, and nothing else.

    `watch` says which workspace this tab is reading, `subscribe` and
    `unsubscribe` say which records of it to hear about.
    """
    while True:
        try:
            message = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except Exception as e:  # noqa: BLE001 - a client sending nonsense loses its socket, not the worker
            logger.debug("Error reading a WebSocket frame: %s", e)

            return

        event_type = message.get("type")
        data = message.get("data") or {}

        if event_type == "heartbeat":
            continue

        if event_type == "watch":
            workspace = await workspace_of(user, data.get("workspace"))
            await _apply(broadcaster, manager.watch(connection, workspace.id if workspace else None))
        elif event_type == "subscribe":
            manager.subscribe(connection, _channels(data))
        elif event_type == "unsubscribe":
            manager.unsubscribe(connection, _channels(data))


async def _apply(broadcaster: WebSocketBroadcaster, change: WorkspaceChange) -> None:
    """Follow what this process now serves, and let go of what it does not.

    A worker is woken for the workspaces it holds a socket for, and for no
    other: that is what keeps one event from costing something on every worker.
    """
    if change.added is None and change.removed is None:
        return

    await broadcaster.follow(change.added)
    await broadcaster.unfollow(change.removed)


def _channels(data: dict[str, Any]) -> list[str]:
    """The channels a frame names: `engram` for a list, `engram:42` for a record.

    Only channels of a registered model are kept: a client cannot invent one and
    make itself heard on it.
    """
    asked = data.get("channels") or ([data["channel"]] if isinstance(data.get("channel"), str) else [])
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

    try:
        await websocket.send_json({"type": "auth_error", "data": {"message": reason}})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    except Exception as e:  # noqa: BLE001 - the socket may already be gone
        logger.debug("Cannot close the refused socket: %s", e)


__all__ = [
    "router",
    "websocket_endpoint",
]
