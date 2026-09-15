# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The realtime layer: local delivery, and the bridge between workers.

A socket is held by one process while an event is raised in whichever process
served the request, so a broadcast travels through PostgreSQL NOTIFY/LISTEN and
comes back to every worker. These tests exercise the real round-trip against
Postgres, plus the two things that decide whether an event survives it: a
payload too large for NOTIFY, and a worker with nothing to serve.

The HTTP test client cannot speak WebSocket, so the sockets are fakes and the
endpoint is covered at its seams.
"""

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import WebSocketDisconnect

from fastedgy.api.realtime import _scope, websocket_endpoint
from fastedgy.bus import Bus
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.orm import Database
from fastedgy.orm.filter import R
from fastedgy.realtime import broadcaster as broadcaster_module
from fastedgy.realtime.auth import RealtimeAuth
from fastedgy.realtime.broadcaster import MAX_PAYLOAD, WebSocketBroadcaster
from fastedgy.realtime.events import OnRealtimeDeliveredEvent, OnRealtimeDisconnectEvent, OnRealtimeFrameEvent
from fastedgy.realtime.manager import WebSocketManager
from fastedgy.test.factories import auth_token, create_user, create_workspace, create_workspace_user
from fastedgy.test.models.realtime import (
    RtChild,
    RtMember,
    RtNote,
    RtOwned,
    RtPost,
    RtProject,
    RtProjectMember,
    RtReaction,
    RtRecord,
    RtSecret,
    RtTask,
    RtThread,
)


class FakeWebSocket:
    """Records the frames it is sent; refuses them all when dead."""

    def __init__(self, dead: bool = False) -> None:
        self.sent: list[dict] = []
        self.dead = dead
        self.closed: int | None = None

    async def send_json(self, message: dict) -> None:
        if self.dead:
            raise RuntimeError("socket is dead")

        self.sent.append(message)

    async def close(self, code: int = 1000) -> None:
        self.closed = code


class ScriptedWebSocket(FakeWebSocket):
    """Plays a handshake then frames, and then leaves, or waits to be closed."""

    def __init__(self, handshake: str | Exception, frames: list[Any], hold: bool = False) -> None:
        super().__init__()
        self.script: list[Any] = [handshake, *frames]
        self.hold = hold
        self.gone = asyncio.Event()

    async def accept(self) -> None:
        return None

    async def receive_text(self) -> str:
        if not self.script:
            if self.hold:
                await self.gone.wait()

            raise WebSocketDisconnect()

        frame = self.script.pop(0)

        if isinstance(frame, Exception):
            raise frame

        return frame if isinstance(frame, str) else json.dumps(frame)

    async def close(self, code: int = 1000) -> None:
        await super().close(code)
        self.gone.set()


@dataclass
class ScopeEnv:
    scope: Any
    admin: Any


async def wait_until(predicate, timeout: float = 3.0, interval: float = 0.02) -> bool:
    elapsed = 0.0

    while elapsed < timeout:
        if predicate():
            return True

        await asyncio.sleep(interval)
        elapsed += interval

    return predicate()


def tuned(**overrides) -> BaseSettings:
    """The application's settings with a few realtime knobs moved.

    A copy rather than an override: the service the application built already
    read the originals, and a test wants its own timings without reaching into
    what the rest of the suite is using.
    """
    return get_service(BaseSettings).model_copy(update=overrides)


def local_manager(**overrides) -> WebSocketManager:
    """A manager of this test's own, holding nobody else's sockets."""
    return WebSocketManager(tuned(**overrides))


def unstarted(**overrides) -> WebSocketBroadcaster:
    return WebSocketBroadcaster(tuned(**overrides), get_service(Database), local_manager())


@pytest.fixture
async def scope_env(setup_db) -> ScopeEnv:
    scope = await create_workspace(slug="acme", name="Acme")
    admin = await create_user(email="admin@example.io", name="Admin")
    await create_workspace_user(admin, scope)

    return ScopeEnv(scope=scope, admin=admin)


@pytest.fixture
async def broadcaster(setup_db, request) -> AsyncIterator[WebSocketBroadcaster]:
    """A broadcaster on a channel of its own, with timings a test can wait on.

    Its own channel so it never races the application's, while still going
    through the real NOTIFY/LISTEN round-trip.
    """
    channel = "ws_test_" + re.sub(r"\W+", "_", request.node.name)[:40]
    instance = WebSocketBroadcaster(
        tuned(
            realtime_channel=channel,
            realtime_heartbeat_interval=0.2,
            realtime_heartbeat_timeout=2.0,
            realtime_reconnect_backoff_start=0.05,
            realtime_reconnect_backoff_max=0.2,
            realtime_supervise_interval=0.1,
        ),
        get_service(Database),
        get_service(WebSocketManager),
    )
    await instance.start()
    await instance.wait_listening()

    yield instance

    await instance.stop()


def _empty(manager: WebSocketManager) -> None:
    for connection in [c for holders in manager._by_user.values() for c in holders]:
        manager.disconnect(connection)


async def hold(ws_manager, broadcaster, scope_id: int, channels: list[str] | None = None, user_id: int = 1):
    """A socket of this worker, on a scope the broadcaster listens to.

    Holding a socket and hearing about the scope go together: the endpoint
    does both, and so does this.
    """
    socket = FakeWebSocket()
    connection = ws_manager.connect(user_id, socket)
    change = ws_manager.watch(connection, scope_id)

    await broadcaster.follow(change.added)

    if channels:
        ws_manager.subscribe(connection, channels)

    return socket


@pytest.fixture
def ws_manager(setup_db) -> Any:
    """The application's manager, emptied around each test."""
    manager = get_service(WebSocketManager)
    _empty(manager)

    yield manager

    _empty(manager)


async def test_only_the_sockets_watching_that_scope_are_served() -> None:
    manager = local_manager()
    served, other = FakeWebSocket(), FakeWebSocket()

    manager.watch(manager.connect(1, served), 7)
    manager.watch(manager.connect(2, other), 8)

    reached = await manager.deliver_to_scope(7, "rt_record.updated", {"id": 1})

    assert reached == {1}
    assert len(served.sent) == 1
    assert other.sent == []


async def test_two_tabs_on_two_scopes_hear_their_own() -> None:
    """The scope is per socket, not per account: the URL says which."""
    manager = local_manager()
    first, second = FakeWebSocket(), FakeWebSocket()

    manager.watch(manager.connect(1, first), 7)
    manager.watch(manager.connect(1, second), 8)

    await manager.deliver_to_scope(7, "rt_record.updated", {"id": 1})

    assert len(first.sent) == 1
    assert second.sent == []


async def test_a_dead_socket_is_dropped_rather_than_counted() -> None:
    manager = local_manager()
    dead = FakeWebSocket(dead=True)

    manager.watch(manager.connect(1, dead), 7)

    assert await manager.deliver_to_scope(7, "rt_record.updated", {"id": 1}) == set()
    assert manager.is_idle


async def test_a_worker_with_no_socket_does_nothing_with_a_broadcast(ws_manager, monkeypatch) -> None:
    """Most workers hold nothing for most events: nothing is even parsed."""
    broadcaster = get_service(WebSocketBroadcaster)
    parsed = []

    monkeypatch.setattr("json.loads", lambda *args, **kwargs: parsed.append(args) or {})

    await broadcaster._handle_notify('{"target": "scope"}')

    assert parsed == []


async def test_an_event_reaches_the_sockets_of_every_worker(broadcaster, ws_manager) -> None:
    """The point of the bridge: a write here is heard by a socket held there."""
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_scope(42, "rt_record.updated", {"id": 1})

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0] == {"type": "rt_record.updated", "data": {"id": 1}}


async def test_an_event_reaches_one_account_wherever_it_is_connected(broadcaster, ws_manager) -> None:
    socket = FakeWebSocket()
    ws_manager.connect(5, socket)

    await broadcaster.broadcast_to_user(5, "user.updated", {"id": 5})

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0] == {"type": "user.updated", "data": {"id": 5}}


async def test_an_oversized_event_still_arrives_without_its_data(broadcaster, ws_manager) -> None:
    """NOTIFY refuses 8000 bytes outright: telling less beats telling nobody."""
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_scope(42, "rt_record.updated", {"content": "x" * (MAX_PAYLOAD * 2)})

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0]["truncated"] is True
    assert socket.sent[0]["data"] is None


async def test_an_event_that_fits_keeps_its_data(broadcaster, ws_manager) -> None:
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_scope(42, "rt_record.updated", {"content": "short"})

    assert await wait_until(lambda: bool(socket.sent))
    assert "truncated" not in socket.sent[0]
    assert socket.sent[0]["data"] == {"content": "short"}


def _record_broadcasts(monkeypatch) -> list[dict]:
    """Every record announcement this test causes, as it left the model layer."""
    announced: list[dict] = []

    async def record(scope_id, model, record_id, action, extra=None, related_channels=None, meta=None) -> None:
        announced.append(
            {
                "scope": scope_id,
                "model": model,
                "id": record_id,
                "action": action,
                "extra": extra or {},
                "channels": related_channels or [],
                "meta": meta or {},
            }
        )

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_record", record)

    return announced


def _user_broadcasts(monkeypatch) -> list[dict]:
    announced: list[dict] = []

    async def record(user_ids, event_type, data, channels=None, meta=None) -> None:
        announced.append(
            {
                "users": sorted(user_ids),
                "event": event_type,
                "data": data,
                "channels": channels or [],
                "meta": meta or {},
            }
        )

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_to_users", record)

    return announced


def of(announced: list[dict], model: str, action: str | None = None) -> list[dict]:
    return [one for one in announced if one["model"] == model and (action is None or one["action"] == action)]


async def announced_as(announced: list[dict], model: str, action: str | None = None) -> dict:
    """The announcement a write owes, once it has landed.

    Publication happens after the transaction commits, in a task of its own, so
    it is never done by the time the write returns.
    """
    await wait_until(lambda: bool(of(announced, model, action)))
    matched = of(announced, model, action)

    assert matched, f"no {model}.{action} announcement"

    return matched[0]


async def announced_to(announced: list[dict], event: str) -> dict:
    await wait_until(lambda: any(one["event"] == event for one in announced))
    matched = [one for one in announced if one["event"] == event]

    assert matched, f"no {event} announcement"

    return matched[0]


async def nothing_announced(announced: list[dict]) -> None:
    """Long enough that a publication scheduled anyway would have landed."""
    await asyncio.sleep(0.2)

    assert announced == []


async def test_writing_a_record_announces_it(ws_manager, scope_env, monkeypatch) -> None:
    """What the sockets are there for: one client writes, the browsers hear it."""
    announced = _record_broadcasts(monkeypatch)
    scope_id = scope_env.scope.id

    record = RtRecord(workspace=scope_env.scope, name="Mem0")
    await record.save()

    record.name = "Mem0 (revised)"
    await record.save()

    child = RtChild(workspace=scope_env.scope, record=record, label="Summary")
    await child.save()

    created = await announced_as(announced, "rt_record", "created")

    assert (created["scope"], created["id"]) == (scope_id, record.id)
    assert await announced_as(announced, "rt_record", "updated")

    # A child reaches the channel of the record it hangs off.
    written = await announced_as(announced, "rt_child", "created")

    assert written["extra"] == {"record_id": record.id}
    assert written["channels"] == [f"rt_record:{record.id}"]


async def test_deleting_a_record_announces_it(ws_manager, scope_env, monkeypatch) -> None:
    record = RtRecord(workspace=scope_env.scope, name="Zep")
    await record.save()

    announced = _record_broadcasts(monkeypatch)
    await record.delete()

    assert (await announced_as(announced, "rt_record", "deleted"))["id"] == record.id


async def test_a_delete_is_announced_once_its_row_is_gone(ws_manager, scope_env, monkeypatch) -> None:
    """A client reading the record again as soon as it hears must not find it still there."""
    record = RtRecord(workspace=scope_env.scope, name="Zep")
    await record.save()

    rows_when_announced: list[int] = []
    raw_delete = RtRecord.raw_delete

    async def announce(scope_id, model, record_id, action, extra=None, related_channels=None, meta=None) -> None:
        if action == "deleted":
            rows_when_announced.append(await RtRecord.global_query.filter(R("id", "=", record_id)).count())

    # What runs between the signal and the statement, an application's own work
    # in `pre_delete` for one, gives an announcement sent too early its chance.
    async def slow_raw_delete(self, *args, **kwargs):
        await asyncio.sleep(0.2)

        return await raw_delete(self, *args, **kwargs)

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_record", announce)
    monkeypatch.setattr(RtRecord, "raw_delete", slow_raw_delete)
    await record.delete()

    assert await wait_until(lambda: bool(rows_when_announced))
    assert rows_when_announced == [0]


async def test_a_delete_that_removed_no_row_announces_nothing(ws_manager, scope_env, monkeypatch) -> None:
    record = RtRecord(workspace=scope_env.scope, name="Zep")
    await record.save()
    await RtRecord.global_query.filter(R("id", "=", record.id)).delete()
    await asyncio.sleep(0.2)

    announced = _record_broadcasts(monkeypatch)
    await record.delete()
    await nothing_announced(announced)

    assert of(announced, "rt_record", "deleted") == []


async def test_an_announcement_waits_for_the_write_to_commit(ws_manager, scope_env, monkeypatch) -> None:
    """An attempt that rolled back said nothing, and never will.

    Announcing from inside the transaction told the clients about a write that
    did not happen, and told them once per attempt under a serialization replay.
    """
    from fastedgy.orm.transaction import with_transaction

    announced = _record_broadcasts(monkeypatch)

    async def write_then_fail() -> None:
        await RtRecord(workspace=scope_env.scope, name="Never committed").save()

        raise RuntimeError("something later in the request failed")

    with contextlib.suppress(RuntimeError):
        await with_transaction(write_then_fail)

    await nothing_announced(announced)


async def test_a_committed_write_still_announces_from_a_transaction(ws_manager, scope_env, monkeypatch) -> None:
    """The other half of the deferral: what commits is still announced, once."""
    from fastedgy.orm.transaction import with_transaction

    announced = _record_broadcasts(monkeypatch)

    async def write() -> RtRecord:
        record = RtRecord(workspace=scope_env.scope, name="Committed")
        await record.save()

        return record

    record = await with_transaction(write)

    assert (await announced_as(announced, "rt_record", "created"))["id"] == record.id
    assert len(of(announced, "rt_record", "created")) == 1


async def test_an_update_names_the_columns_it_moved(ws_manager, scope_env, monkeypatch) -> None:
    """A view reading none of them has nothing to learn from the event."""
    announced = _record_broadcasts(monkeypatch)

    record = RtRecord(workspace=scope_env.scope, name="Mem0")
    await record.save()

    record.name = "Mem0 (revised)"
    await record.save()

    updated = await announced_as(announced, "rt_record", "updated")

    assert "name" in updated["meta"]["changed"]
    # A row appearing is news to a list whatever its columns are.
    assert "changed" not in (await announced_as(announced, "rt_record", "created"))["meta"]


async def test_a_write_through_update_is_announced_with_what_it_wrote(ws_manager, scope_env, monkeypatch) -> None:
    record = RtRecord(workspace=scope_env.scope, name="Mem0")
    await record.save()
    await asyncio.sleep(0.2)

    announced = _record_broadcasts(monkeypatch)
    await record.update(name="Mem0 (revised)")

    changed = (await announced_as(announced, "rt_record", "updated"))["meta"]["changed"]

    assert "name" in changed
    assert "workspace" not in changed


async def test_a_write_carries_the_client_that_made_it(ws_manager, scope_env, monkeypatch) -> None:
    """So that client can leave its own echo alone rather than re-read what it
    just wrote."""
    from fastedgy.realtime.model import ORIGIN_HEADER
    from fastedgy.test.factories import use_request

    announced = _record_broadcasts(monkeypatch)

    with use_request(headers=[(ORIGIN_HEADER.lower().encode(), b"a-browser-tab")]):
        await RtRecord(workspace=scope_env.scope, name="Mem0").save()

    assert (await announced_as(announced, "rt_record", "created"))["meta"]["origin"] == "a-browser-tab"


async def test_an_oversized_origin_is_left_out(ws_manager, scope_env, monkeypatch) -> None:
    """It travels in a NOTIFY payload: an unbounded one would cost the
    announcement its channels and serve the whole scope instead."""
    from fastedgy.realtime.model import MAX_ORIGIN_LENGTH, ORIGIN_HEADER
    from fastedgy.test.factories import use_request

    announced = _record_broadcasts(monkeypatch)
    oversized = b"x" * (MAX_ORIGIN_LENGTH + 1)

    with use_request(headers=[(ORIGIN_HEADER.lower().encode(), oversized)]):
        await RtRecord(workspace=scope_env.scope, name="Mem0").save()

    assert "origin" not in (await announced_as(announced, "rt_record", "created"))["meta"]


async def test_nothing_is_announced_without_a_scope(ws_manager, setup_db, monkeypatch) -> None:
    """A record no scope owns has nobody watching it."""
    announced = _record_broadcasts(monkeypatch)

    await RtRecord(name="Orphan").save()
    await nothing_announced(announced)


async def test_a_generic_relation_announces_what_it_hangs_off(ws_manager, scope_env, monkeypatch) -> None:
    """A note dropped onto a record is a write like any other."""
    env = scope_env
    record = RtRecord(workspace=env.scope, name="Mem0")
    await record.save()

    announced = _record_broadcasts(monkeypatch)

    note = RtNote(workspace=env.scope, content="Seen", target=record)
    await note.save()

    created = await announced_as(announced, "rt_note", "created")

    # What the model declared to carry: which record it hangs off…
    assert created["extra"] == {"target_model": "rt_record", "target_ref": record.id}
    # …and the channel of that record, so the page reading it hears about this.
    assert created["channels"] == [f"rt_record:{record.id}"]


async def test_a_model_that_never_registered_announces_nothing(ws_manager, scope_env, monkeypatch) -> None:
    """Nothing is realtime by default: a model says so for itself."""
    from fastedgy.test.factories import create_category

    announced = _record_broadcasts(monkeypatch)
    await create_category(name="Nothing to announce", workspace=scope_env.scope)
    await nothing_announced(announced)


async def test_a_model_carries_the_columns_it_declared(ws_manager, scope_env, monkeypatch) -> None:
    """`fields` renames on the way out, and a foreign key gives its id."""
    from fastedgy.realtime.model import registry as realtime_registry

    env = scope_env
    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._fields, "rt_child", {"parent": "record"})

    record = RtRecord(workspace=env.scope, name="Mem0")
    await record.save()

    child = RtChild(workspace=env.scope, record=record, label="Summary")
    await child.save()

    assert (await announced_as(announced, "rt_child"))["extra"] == {"parent": record.id}


async def test_a_relation_that_fans_out_reaches_each_of_its_records(ws_manager, scope_env, monkeypatch) -> None:
    """A to-many is read rather than deduced, which is why it is declared."""
    from fastedgy.realtime.model import registry as realtime_registry

    env = scope_env
    record = RtRecord(workspace=env.scope, name="Mem0")
    await record.save()

    first = RtChild(workspace=env.scope, record=record, label="Summary")
    await first.save()

    second = RtChild(workspace=env.scope, record=record, label="Prices")
    await second.save()

    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._relations, "rt_record", ["children"])

    record.name = "Mem0 (revised)"
    await record.save()

    channels = (await announced_as(announced, "rt_record", "updated"))["channels"]

    assert sorted(channels) == sorted([f"rt_child:{first.id}", f"rt_child:{second.id}"])


async def test_a_relation_that_fans_out_too_far_falls_back_on_the_model(ws_manager, scope_env, monkeypatch) -> None:
    """Naming a thousand records would not fit in a NOTIFY, and a list refreshing is the point."""
    from fastedgy.realtime import model as registry_module
    from fastedgy.realtime.model import registry as realtime_registry

    env = scope_env
    record = RtRecord(workspace=env.scope, name="Mem0")
    await record.save()

    for index in range(3):
        await RtChild(workspace=env.scope, record=record, label=f"Child {index}").save()

    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._relations, "rt_record", ["children"])
    monkeypatch.setattr(registry_module, "MAX_RELATION_CHANNELS", 2)

    record.name = "Mem0 (revised)"
    await record.save()

    assert (await announced_as(announced, "rt_record", "updated"))["channels"] == []


async def test_a_failing_announcement_leaves_the_write_alone(ws_manager, scope_env, monkeypatch) -> None:
    """The write is the point; the announcement is what follows it."""

    async def refuse(*args, **kwargs) -> None:
        raise RuntimeError("no channel today")

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_record", refuse)

    record = RtRecord(workspace=scope_env.scope, name="Mem0")
    await record.save()
    await asyncio.sleep(0.1)

    assert record.id is not None
    assert await RtRecord.global_query.filter(R("id", "=", record.id)).count() == 1


async def test_a_payload_no_trimming_can_save_is_sent_to_the_whole_scope(broadcaster, ws_manager) -> None:
    """Losing the channels over-tells; losing the event tells nobody."""
    # Subscribed to nothing: only a broadcast that gave up its channels reaches it.
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_scope(
        42,
        "rt_child.updated",
        {"content": "x" * (MAX_PAYLOAD * 2)},
        channels=[f"rt_child:{index}" for index in range(MAX_PAYLOAD // 8)],
    )

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0]["truncated"] is True


async def test_a_worker_hears_the_scopes_it_holds_and_no_other(broadcaster, ws_manager) -> None:
    """One event costs nothing on the workers that serve none of it."""
    socket = await hold(ws_manager, broadcaster, 42)
    unheld = FakeWebSocket()
    ws_manager.watch(ws_manager.connect(2, unheld), 99)

    await broadcaster.broadcast_to_scope(99, "rt_record.updated", {"id": 1})
    await asyncio.sleep(0.2)

    assert unheld.sent == []

    await broadcaster.broadcast_to_scope(42, "rt_record.updated", {"id": 2})

    assert await wait_until(lambda: bool(socket.sent))


async def test_what_is_known_about_a_write_rides_beside_the_event(broadcaster, ws_manager) -> None:
    """`origin` and `changed` reach the client on the frame itself, not inside
    the record's identity."""
    socket = await hold(ws_manager, broadcaster, 42, ["rt_record"])

    await broadcaster.broadcast_record(
        42,
        "rt_record",
        9,
        "updated",
        meta={"origin": "a-browser-tab", "changed": ["name"]},
    )

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0] == {
        "type": "rt_record.updated",
        "data": {"model": "rt_record", "id": 9},
        "origin": "a-browser-tab",
        "changed": ["name"],
    }


async def test_a_socket_that_stopped_reading_holds_nobody_up() -> None:
    """Delivery is concurrent and bounded: one stuck client is one dropped client."""
    manager = local_manager(realtime_send_timeout=0.05)
    stuck, reading = FakeWebSocket(), FakeWebSocket()

    async def never(message: dict) -> None:
        await asyncio.sleep(30)

    stuck.send_json = never

    for socket, user_id in ((stuck, 1), (reading, 2)):
        manager.watch(manager.connect(user_id, socket), 7)

    served = await manager.deliver_to_scope(7, "rt_record.updated", {"id": 1})

    assert served == {2}
    assert len(reading.sent) == 1
    # It is gone, so the next event does not wait on it again.
    assert manager.scopes() == [7]
    assert 1 not in manager._by_user
    assert await wait_until(lambda: stuck.closed == 1011)


async def test_a_socket_leaves_nothing_behind_when_it_goes() -> None:
    manager = local_manager()
    connection = manager.connect(1, FakeWebSocket())

    manager.watch(connection, 7)
    manager.subscribe(connection, ["rt_record", "rt_record:42"])

    change = manager.disconnect(connection)

    assert change.removed == 7
    assert manager.is_idle
    assert manager._by_scope == {}
    assert manager._by_channel == {}


async def test_an_account_hears_about_itself_and_nobody_else_does(ws_manager, scope_env, monkeypatch) -> None:
    """Addressed to the person: they belong to several scopes, and their own
    news is not the business of any of them."""
    to_user = _user_broadcasts(monkeypatch)
    to_scope = _record_broadcasts(monkeypatch)

    owned = RtOwned(workspace=scope_env.scope, user=scope_env.admin, label="A key")
    await owned.save()

    await wait_until(lambda: bool(to_user))

    assert to_user[0]["users"] == [scope_env.admin.id]
    assert to_user[0]["event"] == "rt_owned.created"
    assert to_user[0]["data"] == {"model": "rt_owned", "id": owned.id}
    assert of(to_scope, "rt_owned") == []


async def test_an_action_can_be_turned_off(ws_manager, scope_env, monkeypatch) -> None:
    to_user = _user_broadcasts(monkeypatch)

    owned = RtOwned(workspace=scope_env.scope, user=scope_env.admin, label="A key")
    await owned.save()
    await wait_until(lambda: bool(to_user))
    await owned.delete()
    await asyncio.sleep(0.2)

    assert [one for one in to_user if one["event"].endswith(".created")]
    assert [one for one in to_user if one["event"].endswith(".deleted")] == []


async def test_a_registry_says_what_a_model_declared() -> None:
    from fastedgy.realtime.model import RealtimeRegistry

    other = RealtimeRegistry()
    other.register(type("Thing", (), {}), {"delete": False}, ["colour"])

    assert other.is_enabled("thing", "create")
    assert not other.is_enabled("thing", "delete")
    assert other.fields("thing") == {"colour": "colour"}


async def test_an_unknown_action_is_refused() -> None:
    from fastedgy.realtime.model import RealtimeRegistry

    with pytest.raises(ValueError, match="Unknown realtime actions"):
        RealtimeRegistry().register(type("Thing", (), {}), {"patch": False})


async def test_only_the_sockets_that_asked_for_a_record_hear_about_it() -> None:
    """The scope says who may hear, the channels say who wants to."""
    manager = local_manager()
    reading, listing, elsewhere = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()

    for socket, channel, user_id in (
        (reading, "rt_record:42", 1),
        (listing, "rt_record", 2),
        (elsewhere, "rt_record:7", 3),
    ):
        connection = manager.connect(user_id, socket)
        manager.watch(connection, 1)
        manager.subscribe(connection, [channel])

    served = await manager.deliver_to_scope(
        1,
        "rt_record.updated",
        {"model": "rt_record", "id": 42},
        channels=["rt_record", "rt_record:42"],
    )

    assert served == {1, 2}
    assert elsewhere.sent == []


async def test_leaving_a_scope_drops_what_was_subscribed_there() -> None:
    manager = local_manager()
    connection = manager.connect(1, FakeWebSocket())

    manager.watch(connection, 1)
    manager.subscribe(connection, ["rt_record:42"])
    manager.watch(connection, 2)

    assert connection.channels == set()


async def test_a_record_event_reaches_the_socket_that_asked(broadcaster, ws_manager) -> None:
    socket = await hold(ws_manager, broadcaster, 42, ["rt_child:9"])

    await broadcaster.broadcast_record(42, "rt_child", 9, "updated")

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0] == {"type": "rt_child.updated", "data": {"model": "rt_child", "id": 9}}


async def test_a_record_event_skips_a_socket_that_did_not_ask(broadcaster, ws_manager) -> None:
    socket = await hold(ws_manager, broadcaster, 42, ["rt_record"])

    await broadcaster.broadcast_record(42, "rt_child", 9, "updated")
    await asyncio.sleep(0.2)

    assert socket.sent == []


async def test_a_write_reaches_a_watching_socket_the_whole_way_through(ws_manager, scope_env) -> None:
    """The whole chain, on the application's own broadcaster.

    A record is written, the write is announced, it travels through Postgres,
    comes back to this worker and lands in a socket that asked for it. Every
    other test cuts the chain somewhere; this one does not.
    """
    env = scope_env
    broadcaster = get_service(WebSocketBroadcaster)

    await broadcaster.ensure_listening()
    socket = await hold(ws_manager, broadcaster, env.scope.id, ["rt_record"])

    record = RtRecord(workspace=env.scope, name="Mem0")
    await record.save()

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0] == {
        "type": "rt_record.created",
        "data": {"model": "rt_record", "id": record.id},
    }


def test_a_frame_names_what_it_reads_generically() -> None:
    """The protocol says `scope`, whatever the application addresses with it."""
    assert _scope({"scope": "studio-nord"}) == "studio-nord"
    assert _scope({}) is None


async def test_an_account_left_out_hears_nothing_of_its_scope() -> None:
    manager = local_manager()
    author, reader = FakeWebSocket(), FakeWebSocket()

    manager.watch(manager.connect(1, author), 7)
    manager.watch(manager.connect(2, reader), 7)

    served = await manager.deliver_to_scope(7, "rt_record.updated", {"id": 1}, exclude_user_ids=[1])

    assert served == {2}
    assert author.sent == []


async def test_an_account_left_out_stays_left_out_across_workers(broadcaster, ws_manager) -> None:
    author = await hold(ws_manager, broadcaster, 42, user_id=1)
    reader = await hold(ws_manager, broadcaster, 42, user_id=2)

    await broadcaster.broadcast_to_scope(42, "rt_record.updated", {"id": 1}, exclude_user_ids=[1])

    assert await wait_until(lambda: bool(reader.sent))
    await asyncio.sleep(0.2)
    assert author.sent == []


async def test_an_event_reaches_several_accounts_and_no_other(broadcaster, ws_manager) -> None:
    first, second, other = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()

    for user_id, socket in ((5, first), (6, second), (7, other)):
        ws_manager.connect(user_id, socket)

    await broadcaster.broadcast_to_users([5, 6], "rt_post.created", {"model": "rt_post", "id": 1})

    assert await wait_until(lambda: bool(first.sent) and bool(second.sent))
    await asyncio.sleep(0.2)
    assert other.sent == []


async def test_many_accounts_are_announced_over_several_notifies(setup_db, monkeypatch) -> None:
    instance = unstarted()
    published: list[dict] = []

    async def record(payload: str, channel: str | None = None) -> None:
        published.append(json.loads(payload))

    monkeypatch.setattr(broadcaster_module, "MAX_USERS_PER_NOTIFY", 2)
    monkeypatch.setattr(instance, "_notify", record)

    await instance.broadcast_to_users([5, 1, 4, 2, 3, 1], "rt_post.created", {"model": "rt_post", "id": 1})

    assert [one["user_ids"] for one in published] == [[1, 2], [3, 4], [5]]


async def test_an_audience_is_announced_over_several_notifies_and_an_empty_one_not_at_all(
    setup_db, monkeypatch
) -> None:
    instance = unstarted()
    published: list[dict] = []

    async def record(payload: str, channel: str | None = None) -> None:
        published.append(json.loads(payload))

    monkeypatch.setattr(broadcaster_module, "MAX_USERS_PER_NOTIFY", 2)
    monkeypatch.setattr(instance, "_notify", record)

    await instance.broadcast_to_scope(42, "import.finished", {"rows": 3}, audience=[5, 1, 4, 2, 3, 1])
    await instance.broadcast_to_scope(42, "import.finished", {"rows": 3}, audience=[])

    assert [one["only"] for one in published] == [[1, 2], [3, 4], [5]]


async def test_the_accounts_watching_an_event_are_told_to_the_bus(broadcaster, ws_manager) -> None:
    bus = get_service(Bus)
    heard: list[OnRealtimeDeliveredEvent] = []

    async def listener(event: OnRealtimeDeliveredEvent) -> None:
        heard.append(event)

    ws_manager.subscribe(ws_manager.connect(5, FakeWebSocket()), ["rt_thread:3"])
    ws_manager.subscribe(ws_manager.connect(6, FakeWebSocket()), ["rt_thread:4"])
    bus.register(OnRealtimeDeliveredEvent, listener)

    try:
        await broadcaster.broadcast_to_users(
            [5, 6],
            "rt_post.created",
            {"model": "rt_post", "id": 1, "thread": 3},
            channels=["rt_post", "rt_post:1", "rt_thread:3"],
        )

        assert await wait_until(lambda: bool(heard))
    finally:
        bus.unregister(OnRealtimeDeliveredEvent, listener)

    assert heard[0].event_type == "rt_post.created"
    assert heard[0].data == {"model": "rt_post", "id": 1, "thread": 3}
    assert heard[0].watchers == {5: {"rt_thread:3"}}


async def test_an_oversized_record_event_keeps_what_names_it(broadcaster, ws_manager) -> None:
    socket = await hold(ws_manager, broadcaster, 42, ["rt_record"])

    await broadcaster.broadcast_record(42, "rt_record", 9, "updated", extra={"summary": "x" * (MAX_PAYLOAD * 2)})

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0]["data"] == {"model": "rt_record", "id": 9}
    assert socket.sent[0]["truncated"] is True


async def test_a_date_travels_the_way_the_api_writes_it(broadcaster, ws_manager) -> None:
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_scope(
        42,
        "rt_record.updated",
        {"at": datetime(2026, 9, 15, 12, 30, tzinfo=UTC)},
    )

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0]["data"] == {"at": "2026-09-15T12:30:00+00:00"}


async def test_a_worker_listens_once_from_its_first_socket(setup_db) -> None:
    instance = unstarted(realtime_channel="ws_test_first_socket")

    assert not instance.is_listening

    try:
        assert await instance.ensure_listening()

        consumers = list(instance._consumer_tasks)

        assert await instance.ensure_listening()
        assert instance._consumer_tasks == consumers
    finally:
        await instance.stop()

    assert not instance.is_listening


async def test_a_path_reaches_every_account_at_its_end(ws_manager, monkeypatch) -> None:
    announced = _user_broadcasts(monkeypatch)
    alice = await create_user(email="alice@example.io")
    bob = await create_user(email="bob@example.io")
    await create_user(email="carol@example.io")

    thread = RtThread(name="Launch")
    await thread.save()
    await RtMember(thread=thread, user=alice).save()
    await RtMember(thread=thread, user=bob).save()

    post = RtPost(thread=thread, body="Ready?")
    await post.save()

    created = await announced_to(announced, "rt_post.created")

    assert set(created["users"]) == {alice.id, bob.id}
    assert created["data"] == {"model": "rt_post", "id": post.id, "thread": thread.id}
    assert created["channels"] == ["rt_post", f"rt_post:{post.id}", f"rt_thread:{thread.id}"]


async def test_a_path_crosses_foreign_keys_before_it_fans_out(ws_manager, monkeypatch) -> None:
    alice = await create_user(email="alice@example.io")
    thread = RtThread(name="Launch")
    await thread.save()
    await RtMember(thread=thread, user=alice).save()

    post = RtPost(thread=thread, body="Ready?")
    await post.save()

    announced = _user_broadcasts(monkeypatch)
    reaction = RtReaction(post=post, emoji="+1")
    await reaction.save()

    created = await announced_to(announced, "rt_reaction.created")

    assert created["users"] == [alice.id]
    assert created["data"] == {"model": "rt_reaction", "id": reaction.id, "post": post.id}


async def test_an_application_has_a_write_reach_accounts_its_path_does_not_name(ws_manager, monkeypatch) -> None:
    alice = await create_user(email="alice@example.io")
    agent = await create_user(email="agent@example.io")
    thread = RtThread(name="Launch")
    await thread.save()
    await RtMember(thread=thread, user=alice).save()

    assert agent.id is not None

    agent_id = agent.id

    async def with_the_agent(event_type: str, data: Any, user_ids: set[int]) -> set[int]:
        return user_ids | {agent_id} if data["model"] == "rt_post" else user_ids

    monkeypatch.setattr(get_service(RealtimeAuth), "recipients", with_the_agent)
    announced = _user_broadcasts(monkeypatch)
    post = RtPost(thread=thread, body="Ready?")
    await post.save()

    created = await announced_to(announced, "rt_post.created")

    assert set(created["users"]) == {alice.id, agent_id}


async def test_who_hears_a_deletion_is_asked_while_its_row_is_still_there(ws_manager, monkeypatch) -> None:
    alice = await create_user(email="alice@example.io")
    thread = RtThread(name="Launch")
    await thread.save()
    await RtMember(thread=thread, user=alice).save()
    post = RtPost(thread=thread, body="Ready?")
    await post.save()
    still_there: list[bool] = []

    async def reading_the_row(event_type: str, data: Any, user_ids: set[int]) -> set[int]:
        if event_type == "rt_post.deleted":
            still_there.append(await RtPost.global_query.filter(R("id", "=", data["id"])).exists())

        return user_ids

    monkeypatch.setattr(get_service(RealtimeAuth), "recipients", reading_the_row)
    announced = _user_broadcasts(monkeypatch)
    await post.delete()

    deleted = await announced_to(announced, "rt_post.deleted")

    assert still_there == [True]
    assert deleted["users"] == [alice.id]


async def test_a_write_whose_recipients_cannot_be_read_is_announced_to_nobody(ws_manager, monkeypatch) -> None:
    alice = await create_user(email="alice@example.io")
    thread = RtThread(name="Launch")
    await thread.save()
    await RtMember(thread=thread, user=alice).save()

    async def unreadable(event_type: str, data: Any, user_ids: set[int]) -> set[int]:
        raise RuntimeError("The directory is down")

    monkeypatch.setattr(get_service(RealtimeAuth), "recipients", unreadable)
    announced = _user_broadcasts(monkeypatch)
    post = RtPost(thread=thread, body="Ready?")
    await post.save()
    await nothing_announced(announced)

    assert post.id is not None
    assert [one for one in announced if one["event"] == "rt_post.created"] == []


async def test_a_delete_reaches_the_accounts_it_had_before_its_links_went(ws_manager, monkeypatch) -> None:
    alice = await create_user(email="alice@example.io")
    thread = RtThread(name="Launch")
    await thread.save()
    await RtMember(thread=thread, user=alice).save()

    announced = _user_broadcasts(monkeypatch)
    await thread.delete()

    assert (await announced_to(announced, "rt_thread.deleted"))["users"] == [alice.id]


async def test_a_path_that_reaches_nobody_announces_nothing(ws_manager, monkeypatch) -> None:
    thread = RtThread(name="Empty")
    await thread.save()

    announced = _user_broadcasts(monkeypatch)
    await RtPost(thread=thread, body="Anyone?").save()

    await nothing_announced(announced)


async def test_a_frame_of_the_application_goes_to_the_bus(ws_manager, scope_env) -> None:
    bus = get_service(Bus)
    heard: list[tuple] = []

    async def on_frame(event: OnRealtimeFrameEvent) -> None:
        heard.append(("frame", event.event_type, event.data, event.connection.user_id))

    async def on_disconnect(event: OnRealtimeDisconnectEvent) -> None:
        heard.append(("gone", event.user.id))

    admin = scope_env.admin
    socket: Any = ScriptedWebSocket(
        json.dumps({"type": "authenticate", "data": {"token": auth_token(admin), "scope": "acme"}}),
        [{"type": "heartbeat"}, {"type": "location.live_start", "data": {"device_id": 3}}],
    )

    bus.register(OnRealtimeFrameEvent, on_frame)
    bus.register(OnRealtimeDisconnectEvent, on_disconnect)

    try:
        await websocket_endpoint(
            socket,
            get_service(BaseSettings),
            ws_manager,
            get_service(WebSocketBroadcaster),
            get_service(RealtimeAuth),
        )
    finally:
        bus.unregister(OnRealtimeFrameEvent, on_frame)
        bus.unregister(OnRealtimeDisconnectEvent, on_disconnect)

    assert socket.sent[0] == {"type": "auth_success", "data": {"user_id": admin.id, "scope": "acme"}}
    assert heard == [("frame", "location.live_start", {"device_id": 3}, admin.id), ("gone", admin.id)]
    assert ws_manager.is_idle


async def test_a_socket_naming_no_scope_reads_the_one_the_application_resolves(ws_manager, scope_env) -> None:
    class DefaultScope(RealtimeAuth):
        async def scope_of(self, user: Any, scope: Any) -> Any:
            return await super().scope_of(user, scope or "acme")

    admin = scope_env.admin
    socket: Any = ScriptedWebSocket(json.dumps({"type": "authenticate", "data": {"token": auth_token(admin)}}), [])

    await websocket_endpoint(
        socket,
        get_service(BaseSettings),
        ws_manager,
        get_service(WebSocketBroadcaster),
        DefaultScope(),
    )

    assert socket.sent[0] == {"type": "auth_success", "data": {"user_id": admin.id, "scope": "acme"}}


async def _serve(socket: Any, manager: WebSocketManager, auth: RealtimeAuth | None = None, **overrides: Any) -> None:
    await websocket_endpoint(
        socket,
        tuned(**overrides),
        manager,
        get_service(WebSocketBroadcaster),
        auth or get_service(RealtimeAuth),
    )


def _handshake(user: Any, scope: str | None = "acme") -> str:
    return json.dumps({"type": "authenticate", "data": {"token": auth_token(user), "scope": scope}})


@pytest.mark.parametrize(
    "handshake",
    [
        KeyError("text"),
        "[]",
        "null",
        "[" * 100_000,
        json.dumps({"type": "authenticate", "data": "a-token"}),
        json.dumps({"type": "authenticate", "data": {"token": 42}}),
        json.dumps({"type": "authenticate", "data": {"token": "x" * 70_000}}),
    ],
)
async def test_a_malformed_handshake_is_refused_rather_than_raised(ws_manager, handshake) -> None:
    socket: Any = ScriptedWebSocket(handshake, [])

    await _serve(socket, ws_manager)

    assert socket.sent[0]["type"] == "auth_error"
    assert socket.closed == 1008


async def test_a_malformed_frame_never_raises_out_of_the_socket(ws_manager, scope_env) -> None:
    handshake = json.dumps({"type": "authenticate", "data": {"token": auth_token(scope_env.admin), "scope": "acme"}})
    last = {"type": "subscribe", "data": {"channels": ["rt_record"]}}
    socket: Any = ScriptedWebSocket(
        handshake,
        [
            {"type": "watch", "data": "acme"},
            {"type": "subscribe", "data": {"channels": 42}},
            {"type": "location.live_start", "data": ["not", "an", "object"]},
            ["not", "an", "object"],
            last,
        ],
    )

    await _serve(socket, ws_manager)

    assert socket.sent[0]["type"] == "auth_success"
    assert socket.script == [last]
    assert ws_manager.is_idle


async def test_a_client_gone_before_its_answer_leaves_nothing_behind(ws_manager, scope_env) -> None:
    handshake = json.dumps({"type": "authenticate", "data": {"token": auth_token(scope_env.admin), "scope": "acme"}})
    socket: Any = ScriptedWebSocket(handshake, [])
    socket.dead = True

    await _serve(socket, ws_manager)

    assert ws_manager.is_idle


async def test_a_socket_whose_bearer_stopped_standing_for_its_account_is_refused(
    ws_manager, scope_env, monkeypatch
) -> None:
    auth = RealtimeAuth()
    socket: Any = ScriptedWebSocket(_handshake(scope_env.admin), [], hold=True)
    serving = asyncio.create_task(_serve(socket, ws_manager, auth, realtime_recheck_interval=0.05))

    assert await wait_until(lambda: not ws_manager.is_idle)

    async def nobody(token: str) -> None:
        return None

    monkeypatch.setattr(auth, "user_of_token", nobody)
    await asyncio.wait_for(serving, timeout=3.0)

    assert socket.sent[-1] == {"type": "auth_error", "data": {"message": "Invalid authentication token"}}
    assert socket.closed == 1008
    assert ws_manager.is_idle


async def test_a_socket_leaves_the_scope_its_account_lost(ws_manager, scope_env) -> None:
    from fastedgy.depends.security import find_workspace_user_model

    admin = scope_env.admin
    socket: Any = ScriptedWebSocket(_handshake(admin), [], hold=True)
    serving = asyncio.create_task(_serve(socket, ws_manager))

    assert await wait_until(lambda: not ws_manager.is_idle)

    connection = next(iter(ws_manager._by_user[admin.id]))
    scope_user_model = find_workspace_user_model()

    assert connection.scope_id == scope_env.scope.id
    assert scope_user_model is not None

    await scope_user_model.global_query.filter(R("user", "=", admin.id)).delete()
    ws_manager.recheck([admin.id])

    assert await wait_until(lambda: connection.scope_id is None)
    assert ws_manager.scopes() == []

    await socket.close()
    await asyncio.wait_for(serving, timeout=3.0)

    assert all(frame["type"] != "auth_error" for frame in socket.sent)


async def test_a_socket_whose_first_watch_fails_leaves_nothing_behind(ws_manager, scope_env, monkeypatch) -> None:
    async def refusing(added: Any) -> None:
        if added is not None:
            raise RuntimeError("LISTEN refused")

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "follow", refusing)
    socket: Any = ScriptedWebSocket(_handshake(scope_env.admin), [], hold=True)

    with pytest.raises(RuntimeError):
        await asyncio.wait_for(_serve(socket, ws_manager), timeout=3.0)

    assert ws_manager.is_idle


async def test_a_check_answered_late_never_undoes_a_newer_watch(ws_manager, scope_env, monkeypatch) -> None:
    """A check reading the scope before a `watch` and applying it after would put the socket back."""
    auth = RealtimeAuth()
    resolve = auth.scope_of
    watch = ws_manager.watch
    resolved = 0
    applied: list[Any] = []

    async def slow_first_check(user: Any, scope: Any) -> Any:
        nonlocal resolved
        resolved += 1

        if resolved == 2:
            await asyncio.sleep(0.3)

        return await resolve(user, scope)

    def recording(connection: Any, scope_id: Any) -> Any:
        applied.append(scope_id)

        return watch(connection, scope_id)

    class LateWatch(ScriptedWebSocket):
        async def receive_text(self) -> str:
            if len(self.script) == 1:
                await asyncio.sleep(0.1)

            return await super().receive_text()

    monkeypatch.setattr(auth, "scope_of", slow_first_check)
    monkeypatch.setattr(ws_manager, "watch", recording)
    socket: Any = LateWatch(_handshake(scope_env.admin), [{"type": "watch", "data": {"scope": None}}], hold=True)
    serving = asyncio.create_task(_serve(socket, ws_manager, auth, realtime_recheck_interval=0.01))

    assert await wait_until(lambda: None in applied)
    await asyncio.sleep(0.4)
    await socket.close()
    await asyncio.wait_for(serving, timeout=3.0)

    assert scope_env.scope.id not in applied[applied.index(None) :]


async def test_a_recheck_reaches_the_sockets_of_every_worker(broadcaster, ws_manager) -> None:
    connection = ws_manager.connect(5, FakeWebSocket())

    await broadcaster.recheck_users([5])

    assert await wait_until(connection.recheck.is_set)


async def test_a_socket_holds_no_more_channels_than_allowed() -> None:
    manager = local_manager(realtime_max_channels=2)
    connection = manager.connect(1, FakeWebSocket())

    manager.watch(connection, 7)
    manager.subscribe(connection, ["rt_record", "rt_record:1", "rt_record:2"])
    manager.subscribe(connection, ["rt_record:1"])

    assert connection.channels == {"rt_record", "rt_record:1"}
    assert set(manager._by_channel) == {(7, "rt_record"), (7, "rt_record:1")}


async def test_a_socket_sending_too_many_frames_is_closed(ws_manager, scope_env) -> None:
    socket: Any = ScriptedWebSocket(_handshake(scope_env.admin), [{"type": "heartbeat"}] * 5, hold=True)

    await asyncio.wait_for(_serve(socket, ws_manager, realtime_frame_limit=3), timeout=3.0)

    assert socket.closed == 1008
    assert len(socket.script) == 1
    assert ws_manager.is_idle


async def test_a_frame_heavier_than_allowed_closes_its_socket(ws_manager, scope_env) -> None:
    heavy = {"type": "heartbeat", "data": {"padding": "x" * 4096}}
    socket: Any = ScriptedWebSocket(_handshake(scope_env.admin), [heavy, {"type": "heartbeat"}], hold=True)

    await asyncio.wait_for(_serve(socket, ws_manager, realtime_max_frame_size=2048), timeout=3.0)

    assert socket.closed == 1009
    assert socket.script == [{"type": "heartbeat"}]
    assert ws_manager.is_idle


async def test_a_record_only_some_members_can_read_reaches_those_members_alone(ws_manager, scope_env) -> None:
    other = await create_user(email="other@example.io", name="Other")
    await create_workspace_user(other, scope_env.scope)
    broadcaster = get_service(WebSocketBroadcaster)

    assert other.id is not None

    await broadcaster.ensure_listening()

    owner_socket = await hold(ws_manager, broadcaster, scope_env.scope.id, ["rt_secret"], user_id=scope_env.admin.id)
    other_socket = await hold(ws_manager, broadcaster, scope_env.scope.id, ["rt_secret"], user_id=other.id)

    await RtSecret(workspace=scope_env.scope, owner=scope_env.admin, label="Vault").save()

    assert await wait_until(lambda: bool(owner_socket.sent))
    await asyncio.sleep(0.2)

    assert owner_socket.sent[0]["type"] == "rt_secret.created"
    assert other_socket.sent == []


async def test_deleting_a_record_only_some_members_can_read_tells_those_members_alone(
    ws_manager, scope_env, monkeypatch
) -> None:
    other = await create_user(email="other@example.io", name="Other")
    await create_workspace_user(other, scope_env.scope)
    secret = RtSecret(workspace=scope_env.scope, owner=scope_env.admin, label="Vault")
    await secret.save()

    audiences: list[Any] = []

    async def announce(
        scope_id, model, record_id, action, extra=None, related_channels=None, meta=None, audience=None
    ) -> None:
        if action == "deleted":
            audiences.append(audience)

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_record", announce)
    await secret.delete()

    assert await wait_until(lambda: bool(audiences))
    assert audiences == [{scope_env.admin.id}]


async def test_deleting_a_membership_has_its_account_checked_at_once(ws_manager, scope_env, monkeypatch) -> None:
    from fastedgy.depends.security import find_workspace_user_model
    from fastedgy.realtime.revocation import watch_revocations

    watch_revocations()
    rechecked: list[list[int]] = []

    async def recheck(user_ids) -> None:
        rechecked.append(list(user_ids))

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "recheck_users", recheck)

    scope_user_model: Any = find_workspace_user_model()
    membership = await scope_user_model.global_query.filter(R("user", "=", scope_env.admin.id)).first()
    await membership.delete()

    assert await wait_until(lambda: bool(rechecked))
    assert rechecked == [[scope_env.admin.id]]


async def test_revoking_an_api_key_has_its_account_checked_at_once(ws_manager, scope_env, monkeypatch) -> None:
    from fastedgy.models.user_api_token import get_user_api_token_model, hash_api_token
    from fastedgy.realtime.revocation import watch_revocations

    watch_revocations()
    token_model: Any = get_user_api_token_model()
    key = token_model(name="Agent", user=scope_env.admin, token_hash=hash_api_token("fet_agent"), token_hint="fet_ag")
    await key.save()

    rechecked: list[list[int]] = []

    async def recheck(user_ids) -> None:
        rechecked.append(list(user_ids))

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "recheck_users", recheck)
    await key.delete()

    assert await wait_until(lambda: bool(rechecked))
    assert rechecked == [[scope_env.admin.id]]


async def _rechecks(monkeypatch) -> list[list[int]]:
    from fastedgy.realtime.revocation import watch_revocations

    watch_revocations()
    rechecked: list[list[int]] = []

    async def recheck(user_ids) -> None:
        rechecked.append(list(user_ids))

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "recheck_users", recheck)

    return rechecked


async def test_deleting_an_account_has_its_sockets_checked_at_once(ws_manager, scope_env, monkeypatch) -> None:
    rechecked = await _rechecks(monkeypatch)
    admin_id = scope_env.admin.id

    await scope_env.admin.delete()

    assert await wait_until(lambda: bool(rechecked))
    assert all(user_ids == [admin_id] for user_ids in rechecked)


async def test_changing_what_a_session_token_names_has_its_account_checked_at_once(
    ws_manager, scope_env, monkeypatch
) -> None:
    rechecked = await _rechecks(monkeypatch)
    admin = scope_env.admin

    await admin.update(name="Renamed")
    await asyncio.sleep(0.2)

    assert rechecked == []

    await admin.update(email="renamed@example.io")

    assert await wait_until(lambda: bool(rechecked))
    assert rechecked == [[admin.id]]


async def test_changing_a_membership_or_a_key_has_its_account_checked_at_once(
    ws_manager, scope_env, monkeypatch
) -> None:
    from fastedgy.depends.security import find_workspace_user_model
    from fastedgy.models.user_api_token import get_user_api_token_model, hash_api_token

    token_model: Any = get_user_api_token_model()
    key = token_model(name="Agent", user=scope_env.admin, token_hash=hash_api_token("fet_agent"), token_hint="fet_ag")
    await key.save()
    scope_user_model: Any = find_workspace_user_model()
    membership = await scope_user_model.global_query.filter(R("user", "=", scope_env.admin.id)).first()
    rechecked = await _rechecks(monkeypatch)

    await key.update(name="Renamed")

    assert await wait_until(lambda: len(rechecked) == 1)

    await membership.update(updated_at=datetime.now(UTC))

    assert await wait_until(lambda: len(rechecked) == 2)
    assert rechecked == [[scope_env.admin.id], [scope_env.admin.id]]


async def test_an_account_holding_as_many_sockets_as_allowed_is_refused_one_more(ws_manager, scope_env) -> None:
    first: Any = ScriptedWebSocket(_handshake(scope_env.admin), [], hold=True)
    serving = asyncio.create_task(_serve(first, ws_manager, realtime_max_sockets_per_user=1))

    assert await wait_until(lambda: not ws_manager.is_idle)

    second: Any = ScriptedWebSocket(_handshake(scope_env.admin), [])
    await _serve(second, ws_manager, realtime_max_sockets_per_user=1)

    assert second.sent == [{"type": "auth_error", "data": {"message": "Too many connections"}}]

    await first.close()
    await asyncio.wait_for(serving, timeout=3.0)


async def test_a_watch_naming_the_scope_already_read_asks_nothing(ws_manager, scope_env, monkeypatch) -> None:
    auth = RealtimeAuth()
    asked: list[Any] = []
    scope_of = auth.scope_of

    async def counting(user: Any, scope: Any) -> Any:
        asked.append(scope)

        return await scope_of(user, scope)

    monkeypatch.setattr(auth, "scope_of", counting)
    socket: Any = ScriptedWebSocket(_handshake(scope_env.admin), [{"type": "watch", "data": {"scope": "acme"}}] * 3)

    await _serve(socket, ws_manager, auth)

    assert asked == ["acme"]


def test_only_a_model_read_narrower_than_its_scope_is_guarded() -> None:
    """The workspace filter every workspaceable model carries is the scope itself."""
    from fastedgy.realtime.access import is_guarded

    assert not is_guarded(RtRecord)
    assert not is_guarded(RtProject)
    assert is_guarded(RtSecret)
    assert is_guarded(RtTask)


async def test_who_reads_a_record_is_asked_of_the_database_in_one_statement(ws_manager, scope_env, monkeypatch) -> None:
    from fastedgy.realtime.access import readers

    for index in range(3):
        member = await create_user(email=f"member{index}@example.io", name=f"Member {index}")
        await create_workspace_user(member, scope_env.scope)

    secret = RtSecret(workspace=scope_env.scope, owner=scope_env.admin, label="Vault")
    await secret.save()

    registry: Any = RtSecret.meta.registry
    database = registry.database
    asked: list[str] = []

    for name in ("fetch_one", "fetch_val"):
        original = getattr(database, name)

        async def counting(*args: Any, _original: Any = original, _name: str = name, **kwargs: Any) -> Any:
            asked.append(_name)

            return await _original(*args, **kwargs)

        monkeypatch.setattr(database, name, counting)

    assert await readers(RtSecret, secret.id, scope_env.scope.id) == {scope_env.admin.id}
    assert asked == ["fetch_one"]


async def _two_members_listening(ws_manager, scope_env) -> tuple[Any, FakeWebSocket, FakeWebSocket]:
    other = await create_user(email="other@example.io", name="Other")
    await create_workspace_user(other, scope_env.scope)
    broadcaster = get_service(WebSocketBroadcaster)

    assert other.id is not None

    await broadcaster.ensure_listening()

    owner_socket = await hold(ws_manager, broadcaster, scope_env.scope.id, user_id=scope_env.admin.id)
    other_socket = await hold(ws_manager, broadcaster, scope_env.scope.id, user_id=other.id)

    return broadcaster, owner_socket, other_socket


def _heard(socket: FakeWebSocket, event_type: str) -> bool:
    return any(frame["type"] == event_type for frame in socket.sent)


async def test_an_event_about_a_record_reaches_only_those_who_read_it(ws_manager, scope_env) -> None:
    secret = RtSecret(workspace=scope_env.scope, owner=scope_env.admin, label="Vault")
    await secret.save()
    broadcaster, owner_socket, other_socket = await _two_members_listening(ws_manager, scope_env)

    await broadcaster.broadcast_to_scope(scope_env.scope.id, "vault.opened", {}, about=(RtSecret, secret.id))

    assert await wait_until(lambda: _heard(owner_socket, "vault.opened"))
    await asyncio.sleep(0.2)

    assert not _heard(other_socket, "vault.opened")


async def test_an_event_about_a_model_nobody_declared_reaches_nobody(ws_manager, scope_env) -> None:
    broadcaster, owner_socket, other_socket = await _two_members_listening(ws_manager, scope_env)

    await broadcaster.broadcast_to_scope(scope_env.scope.id, "vault.opened", {}, about=("no_such_model", 1))
    await broadcaster.broadcast_to_scope(scope_env.scope.id, "vault.closed", {})

    assert await wait_until(lambda: _heard(owner_socket, "vault.closed"))

    assert not _heard(owner_socket, "vault.opened")
    assert not _heard(other_socket, "vault.opened")


async def test_an_application_decides_who_hears_its_own_events(ws_manager, scope_env, monkeypatch) -> None:
    broadcaster, owner_socket, other_socket = await _two_members_listening(ws_manager, scope_env)

    async def the_owner_alone(scope_id, event_type, data, user_ids, about=None) -> set[int]:
        return {scope_env.admin.id} & user_ids

    monkeypatch.setattr(get_service(RealtimeAuth), "audience", the_owner_alone)
    await broadcaster.broadcast_to_scope(scope_env.scope.id, "import.finished", {"rows": 3})

    assert await wait_until(lambda: _heard(owner_socket, "import.finished"))
    await asyncio.sleep(0.2)

    assert not _heard(other_socket, "import.finished")


async def test_an_event_told_who_may_hear_it_reaches_them_alone(broadcaster, ws_manager) -> None:
    told = await hold(ws_manager, broadcaster, 42, user_id=1)
    untold = await hold(ws_manager, broadcaster, 42, user_id=2)

    await broadcaster.broadcast_to_scope(42, "import.finished", {"rows": 3}, audience=[1])

    assert await wait_until(lambda: _heard(told, "import.finished"))
    await asyncio.sleep(0.2)

    assert not _heard(untold, "import.finished")


async def _shared_project(scope_env) -> tuple[RtProject, Any]:
    outsider = await create_user(email="outsider@example.io", name="Outsider")
    elsewhere = await create_workspace(slug="elsewhere", name="Elsewhere")
    await create_workspace_user(outsider, elsewhere)
    await create_user(email="stranger@example.io", name="Stranger")

    project = RtProject(workspace=scope_env.scope, name="Launch")
    await project.save()
    await RtProjectMember(project=project, user=scope_env.admin).save()
    await RtProjectMember(project=project, user=outsider).save()

    return project, outsider


async def test_a_record_shared_through_its_root_reaches_its_members_in_other_scopes(
    ws_manager, scope_env, monkeypatch
) -> None:
    project, outsider = await _shared_project(scope_env)
    to_users = _user_broadcasts(monkeypatch)

    await RtTask(workspace=scope_env.scope, project=project, label="Kickoff").save()

    assert (await announced_to(to_users, "rt_task.created"))["users"] == [outsider.id]


async def test_deleting_a_shared_record_tells_its_members_in_other_scopes(ws_manager, scope_env, monkeypatch) -> None:
    project, outsider = await _shared_project(scope_env)
    task = RtTask(workspace=scope_env.scope, project=project, label="Kickoff")
    await task.save()

    to_users = _user_broadcasts(monkeypatch)
    await task.delete()

    assert (await announced_to(to_users, "rt_task.deleted"))["users"] == [outsider.id]


async def test_updating_a_shared_record_tells_its_members_in_other_scopes(ws_manager, scope_env, monkeypatch) -> None:
    project, outsider = await _shared_project(scope_env)
    task = RtTask(workspace=scope_env.scope, project=project, label="Kickoff")
    await task.save()
    await asyncio.sleep(0.2)

    to_users = _user_broadcasts(monkeypatch)
    await task.update(label="Launch day")

    assert (await announced_to(to_users, "rt_task.updated"))["users"] == [outsider.id]


async def test_a_member_the_root_refuses_hears_nothing_from_another_scope(ws_manager, scope_env, monkeypatch) -> None:
    project, _ = await _shared_project(scope_env)

    async def refusing(cls: Any, record: Any, user: Any, member: Any) -> bool:
        return False

    monkeypatch.setattr(RtProject, "workspace_shareable_authorize", classmethod(refusing))
    to_users = _user_broadcasts(monkeypatch)
    await RtTask(workspace=scope_env.scope, project=project, label="Kickoff").save()
    await nothing_announced(to_users)

    assert to_users == []


async def test_a_listener_whose_backend_was_killed_comes_back(broadcaster, ws_manager) -> None:
    from sqlalchemy import text

    pid = broadcaster._pg_conn.get_server_pid()

    await get_service(Database).execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

    assert await wait_until(
        lambda: broadcaster._pg_conn is not None and broadcaster._pg_conn.get_server_pid() != pid,
        timeout=10.0,
    )

    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_scope(42, "rt_record.updated", {"id": 1})

    assert await wait_until(lambda: bool(socket.sent), timeout=5.0)


async def test_a_listener_retries_until_a_connection_holds(setup_db, monkeypatch) -> None:
    instance = unstarted(realtime_reconnect_backoff_start=0.01, realtime_reconnect_backoff_max=0.02)
    attempts = {"n": 0}
    connected = asyncio.Event()

    async def flaky() -> None:
        attempts["n"] += 1

        if attempts["n"] < 3:
            raise RuntimeError("connection refused")

        connected.set()
        await instance._shutdown.wait()

    monkeypatch.setattr(instance, "_listen_once", flaky)
    task = asyncio.create_task(instance._listen())

    assert await wait_until(connected.is_set, timeout=2.0)
    assert attempts["n"] == 3

    instance._shutdown.set()
    await asyncio.wait_for(task, timeout=2.0)


async def _listen_while_dropped(instance: WebSocketBroadcaster, monkeypatch, database_answers: bool) -> None:
    attempts = {"n": 0}
    done = asyncio.Event()

    async def dropped() -> None:
        attempts["n"] += 1

        if attempts["n"] >= 5:
            done.set()
            await instance._shutdown.wait()

            return

        raise RuntimeError("the listen socket was dropped")

    async def reachable() -> bool:
        return database_answers

    monkeypatch.setattr(instance, "_listen_once", dropped)
    monkeypatch.setattr(instance, "_database_reachable", reachable)
    task = asyncio.create_task(instance._listen())

    assert await wait_until(done.is_set, timeout=2.0)

    instance._shutdown.set()
    await asyncio.wait_for(task, timeout=2.0)


def _listener_levels(caplog) -> list[str]:
    return [one.levelname for one in caplog.records if "Broadcaster listener" in one.getMessage()]


async def test_a_listener_stays_a_warning_while_the_database_is_down(setup_db, monkeypatch, caplog) -> None:
    instance = unstarted(realtime_reconnect_backoff_start=0.01, realtime_reconnect_backoff_max=0.02)

    with caplog.at_level(logging.WARNING, logger="fastedgy.realtime.broadcaster"):
        await _listen_while_dropped(instance, monkeypatch, database_answers=False)

    levels = _listener_levels(caplog)

    assert levels
    assert set(levels) == {"WARNING"}


async def test_a_listener_is_an_error_once_it_stays_down_while_the_database_answers(
    setup_db, monkeypatch, caplog
) -> None:
    instance = unstarted(realtime_reconnect_backoff_start=0.01, realtime_reconnect_backoff_max=0.02)

    with caplog.at_level(logging.WARNING, logger="fastedgy.realtime.broadcaster"):
        await _listen_while_dropped(instance, monkeypatch, database_answers=True)

    levels = _listener_levels(caplog)

    assert levels[:2] == ["WARNING", "WARNING"]
    assert levels[2:]
    assert set(levels[2:]) == {"ERROR"}


async def test_a_supervisor_restarts_a_listener_that_died(setup_db, monkeypatch) -> None:
    instance = unstarted(realtime_supervise_interval=0.05)
    starts = {"n": 0}

    async def dying() -> None:
        starts["n"] += 1

    monkeypatch.setattr(instance, "_listen", dying)
    await instance.start()

    try:
        assert await wait_until(lambda: starts["n"] >= 2, timeout=2.0)
    finally:
        await instance.stop()


async def test_a_column_the_write_did_not_carry_is_never_read_back(ws_manager, scope_env, monkeypatch) -> None:
    from fastedgy.orm.transaction import with_transaction
    from fastedgy.realtime.model import registry as realtime_registry

    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._fields, "rt_child", {"label": "label"})

    async def write() -> RtChild:
        child = RtChild(workspace=scope_env.scope)
        await child.save()

        return child

    child = await with_transaction(write)
    created = await announced_as(announced, "rt_child", "created")

    assert created["id"] == child.id
    assert created["extra"] == {"label": None}
