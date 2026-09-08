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
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest

from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.orm import Database
from fastedgy.orm.filter import R
from fastedgy.realtime.broadcaster import MAX_PAYLOAD, WebSocketBroadcaster
from fastedgy.realtime.manager import WebSocketManager
from fastedgy.test.factories import create_user, create_workspace, create_workspace_user
from fastedgy.test.models.realtime import RtChild, RtNote, RtOwned, RtRecord


class FakeWebSocket:
    """Records the frames it is sent; refuses them all when dead."""

    def __init__(self, dead: bool = False) -> None:
        self.sent: list[dict] = []
        self.dead = dead

    async def send_json(self, message: dict) -> None:
        if self.dead:
            raise RuntimeError("socket is dead")

        self.sent.append(message)


@dataclass
class WorkspaceEnv:
    workspace: Any
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


@pytest.fixture
async def workspace_env(setup_db) -> WorkspaceEnv:
    workspace = await create_workspace(slug="acme", name="Acme")
    admin = await create_user(email="admin@example.io", name="Admin")
    await create_workspace_user(admin, workspace)

    return WorkspaceEnv(workspace=workspace, admin=admin)


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


async def hold(ws_manager, broadcaster, workspace_id: int, channels: list[str] | None = None, user_id: int = 1):
    """A socket of this worker, on a workspace the broadcaster listens to.

    Holding a socket and hearing about the workspace go together: the endpoint
    does both, and so does this.
    """
    socket = FakeWebSocket()
    connection = ws_manager.connect(user_id, socket)
    change = ws_manager.watch(connection, workspace_id)

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


async def test_only_the_sockets_watching_that_workspace_are_served() -> None:
    manager = local_manager()
    served, other = FakeWebSocket(), FakeWebSocket()

    manager.watch(manager.connect(1, served), 7)
    manager.watch(manager.connect(2, other), 8)

    reached = await manager.deliver_to_workspace(7, "rt_record.updated", {"id": 1})

    assert reached == {1}
    assert len(served.sent) == 1
    assert other.sent == []


async def test_two_tabs_on_two_workspaces_hear_their_own() -> None:
    """The workspace is per socket, not per account: the URL says which."""
    manager = local_manager()
    first, second = FakeWebSocket(), FakeWebSocket()

    manager.watch(manager.connect(1, first), 7)
    manager.watch(manager.connect(1, second), 8)

    await manager.deliver_to_workspace(7, "rt_record.updated", {"id": 1})

    assert len(first.sent) == 1
    assert second.sent == []


async def test_a_dead_socket_is_dropped_rather_than_counted() -> None:
    manager = local_manager()
    dead = FakeWebSocket(dead=True)

    manager.watch(manager.connect(1, dead), 7)

    assert await manager.deliver_to_workspace(7, "rt_record.updated", {"id": 1}) == set()
    assert manager.is_idle


async def test_a_worker_with_no_socket_does_nothing_with_a_broadcast(ws_manager, monkeypatch) -> None:
    """Most workers hold nothing for most events: nothing is even parsed."""
    broadcaster = get_service(WebSocketBroadcaster)
    parsed = []

    monkeypatch.setattr("json.loads", lambda *args, **kwargs: parsed.append(args) or {})

    await broadcaster._handle_notify('{"target": "workspace"}')

    assert parsed == []


async def test_an_event_reaches_the_sockets_of_every_worker(broadcaster, ws_manager) -> None:
    """The point of the bridge: a write here is heard by a socket held there."""
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_workspace(42, "rt_record.updated", {"id": 1})

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

    await broadcaster.broadcast_to_workspace(42, "rt_record.updated", {"content": "x" * (MAX_PAYLOAD * 2)})

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0]["truncated"] is True
    assert socket.sent[0]["data"] is None


async def test_an_event_that_fits_keeps_its_data(broadcaster, ws_manager) -> None:
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_workspace(42, "rt_record.updated", {"content": "short"})

    assert await wait_until(lambda: bool(socket.sent))
    assert "truncated" not in socket.sent[0]
    assert socket.sent[0]["data"] == {"content": "short"}


def _record_broadcasts(monkeypatch) -> list[dict]:
    """Every record announcement this test causes, as it left the model layer."""
    announced: list[dict] = []

    async def record(workspace_id, model, record_id, action, extra=None, related_channels=None, meta=None) -> None:
        announced.append(
            {
                "workspace": workspace_id,
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

    async def record(user_id, event_type, data, meta=None) -> None:
        announced.append({"user": user_id, "event": event_type, "data": data, "meta": meta or {}})

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_to_user", record)

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


async def nothing_announced(announced: list[dict]) -> None:
    """Long enough that a publication scheduled anyway would have landed."""
    await asyncio.sleep(0.2)

    assert announced == []


async def test_writing_a_record_announces_it(ws_manager, workspace_env, monkeypatch) -> None:
    """What the sockets are there for: one client writes, the browsers hear it."""
    announced = _record_broadcasts(monkeypatch)
    workspace_id = workspace_env.workspace.id

    record = RtRecord(workspace=workspace_env.workspace, name="Mem0")
    await record.save()

    record.name = "Mem0 (revised)"
    await record.save()

    child = RtChild(workspace=workspace_env.workspace, record=record, label="Summary")
    await child.save()

    created = await announced_as(announced, "rt_record", "created")

    assert (created["workspace"], created["id"]) == (workspace_id, record.id)
    assert await announced_as(announced, "rt_record", "updated")

    # A child reaches the channel of the record it hangs off.
    written = await announced_as(announced, "rt_child", "created")

    assert written["extra"] == {"record_id": record.id}
    assert written["channels"] == [f"rt_record:{record.id}"]


async def test_deleting_a_record_announces_it(ws_manager, workspace_env, monkeypatch) -> None:
    record = RtRecord(workspace=workspace_env.workspace, name="Zep")
    await record.save()

    announced = _record_broadcasts(monkeypatch)
    await record.delete()

    assert (await announced_as(announced, "rt_record", "deleted"))["id"] == record.id


async def test_an_announcement_waits_for_the_write_to_commit(ws_manager, workspace_env, monkeypatch) -> None:
    """An attempt that rolled back said nothing, and never will.

    Announcing from inside the transaction told the clients about a write that
    did not happen, and told them once per attempt under a serialization replay.
    """
    from fastedgy.orm.transaction import with_transaction

    announced = _record_broadcasts(monkeypatch)

    async def write_then_fail() -> None:
        await RtRecord(workspace=workspace_env.workspace, name="Never committed").save()

        raise RuntimeError("something later in the request failed")

    with contextlib.suppress(RuntimeError):
        await with_transaction(write_then_fail)

    await nothing_announced(announced)


async def test_a_committed_write_still_announces_from_a_transaction(ws_manager, workspace_env, monkeypatch) -> None:
    """The other half of the deferral: what commits is still announced, once."""
    from fastedgy.orm.transaction import with_transaction

    announced = _record_broadcasts(monkeypatch)

    async def write() -> RtRecord:
        record = RtRecord(workspace=workspace_env.workspace, name="Committed")
        await record.save()

        return record

    record = await with_transaction(write)

    assert (await announced_as(announced, "rt_record", "created"))["id"] == record.id
    assert len(of(announced, "rt_record", "created")) == 1


async def test_an_update_names_the_columns_it_moved(ws_manager, workspace_env, monkeypatch) -> None:
    """A view reading none of them has nothing to learn from the event."""
    announced = _record_broadcasts(monkeypatch)

    record = RtRecord(workspace=workspace_env.workspace, name="Mem0")
    await record.save()

    record.name = "Mem0 (revised)"
    await record.save()

    updated = await announced_as(announced, "rt_record", "updated")

    assert "name" in updated["meta"]["changed"]
    # A row appearing is news to a list whatever its columns are.
    assert "changed" not in (await announced_as(announced, "rt_record", "created"))["meta"]


async def test_a_write_carries_the_client_that_made_it(ws_manager, workspace_env, monkeypatch) -> None:
    """So that client can leave its own echo alone rather than re-read what it
    just wrote."""
    from fastedgy.realtime.model import ORIGIN_HEADER
    from fastedgy.test.factories import use_request

    announced = _record_broadcasts(monkeypatch)

    with use_request(headers=[(ORIGIN_HEADER.lower().encode(), b"a-browser-tab")]):
        await RtRecord(workspace=workspace_env.workspace, name="Mem0").save()

    assert (await announced_as(announced, "rt_record", "created"))["meta"]["origin"] == "a-browser-tab"


async def test_an_oversized_origin_is_left_out(ws_manager, workspace_env, monkeypatch) -> None:
    """It travels in a NOTIFY payload: an unbounded one would cost the
    announcement its channels and serve the whole workspace instead."""
    from fastedgy.realtime.model import MAX_ORIGIN_LENGTH, ORIGIN_HEADER
    from fastedgy.test.factories import use_request

    announced = _record_broadcasts(monkeypatch)
    oversized = b"x" * (MAX_ORIGIN_LENGTH + 1)

    with use_request(headers=[(ORIGIN_HEADER.lower().encode(), oversized)]):
        await RtRecord(workspace=workspace_env.workspace, name="Mem0").save()

    assert "origin" not in (await announced_as(announced, "rt_record", "created"))["meta"]


async def test_nothing_is_announced_without_a_workspace(ws_manager, setup_db, monkeypatch) -> None:
    """A record no workspace owns has nobody watching it."""
    announced = _record_broadcasts(monkeypatch)

    await RtRecord(name="Orphan").save()
    await nothing_announced(announced)


async def test_a_generic_relation_announces_what_it_hangs_off(ws_manager, workspace_env, monkeypatch) -> None:
    """A note dropped onto a record is a write like any other."""
    env = workspace_env
    record = RtRecord(workspace=env.workspace, name="Mem0")
    await record.save()

    announced = _record_broadcasts(monkeypatch)

    note = RtNote(workspace=env.workspace, content="Seen", target=record)
    await note.save()

    created = await announced_as(announced, "rt_note", "created")

    # What the model declared to carry: which record it hangs off…
    assert created["extra"] == {"target_model": "rt_record", "target_ref": record.id}
    # …and the channel of that record, so the page reading it hears about this.
    assert created["channels"] == [f"rt_record:{record.id}"]


async def test_a_model_that_never_registered_announces_nothing(ws_manager, workspace_env, monkeypatch) -> None:
    """Nothing is realtime by default: a model says so for itself."""
    from fastedgy.test.factories import create_category

    announced = _record_broadcasts(monkeypatch)
    await create_category(name="Nothing to announce", workspace=workspace_env.workspace)
    await nothing_announced(announced)


async def test_a_model_carries_the_columns_it_declared(ws_manager, workspace_env, monkeypatch) -> None:
    """`fields` renames on the way out, and a foreign key gives its id."""
    from fastedgy.realtime.model import registry as realtime_registry

    env = workspace_env
    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._fields, "rt_child", {"parent": "record"})

    record = RtRecord(workspace=env.workspace, name="Mem0")
    await record.save()

    child = RtChild(workspace=env.workspace, record=record, label="Summary")
    await child.save()

    assert (await announced_as(announced, "rt_child"))["extra"] == {"parent": record.id}


async def test_a_relation_that_fans_out_reaches_each_of_its_records(ws_manager, workspace_env, monkeypatch) -> None:
    """A to-many is read rather than deduced, which is why it is declared."""
    from fastedgy.realtime.model import registry as realtime_registry

    env = workspace_env
    record = RtRecord(workspace=env.workspace, name="Mem0")
    await record.save()

    first = RtChild(workspace=env.workspace, record=record, label="Summary")
    await first.save()

    second = RtChild(workspace=env.workspace, record=record, label="Prices")
    await second.save()

    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._relations, "rt_record", ["children"])

    record.name = "Mem0 (revised)"
    await record.save()

    channels = (await announced_as(announced, "rt_record", "updated"))["channels"]

    assert sorted(channels) == sorted([f"rt_child:{first.id}", f"rt_child:{second.id}"])


async def test_a_relation_that_fans_out_too_far_falls_back_on_the_model(ws_manager, workspace_env, monkeypatch) -> None:
    """Naming a thousand records would not fit in a NOTIFY, and a list refreshing is the point."""
    from fastedgy.realtime import model as registry_module
    from fastedgy.realtime.model import registry as realtime_registry

    env = workspace_env
    record = RtRecord(workspace=env.workspace, name="Mem0")
    await record.save()

    for index in range(3):
        await RtChild(workspace=env.workspace, record=record, label=f"Child {index}").save()

    announced = _record_broadcasts(monkeypatch)
    monkeypatch.setitem(realtime_registry._relations, "rt_record", ["children"])
    monkeypatch.setattr(registry_module, "MAX_RELATION_CHANNELS", 2)

    record.name = "Mem0 (revised)"
    await record.save()

    assert (await announced_as(announced, "rt_record", "updated"))["channels"] == []


async def test_a_failing_announcement_leaves_the_write_alone(ws_manager, workspace_env, monkeypatch) -> None:
    """The write is the point; the announcement is what follows it."""

    async def refuse(*args, **kwargs) -> None:
        raise RuntimeError("no channel today")

    monkeypatch.setattr(get_service(WebSocketBroadcaster), "broadcast_record", refuse)

    record = RtRecord(workspace=workspace_env.workspace, name="Mem0")
    await record.save()
    await asyncio.sleep(0.1)

    assert record.id is not None
    assert await RtRecord.global_query.filter(R("id", "=", record.id)).count() == 1


async def test_a_payload_no_trimming_can_save_is_sent_to_the_whole_workspace(broadcaster, ws_manager) -> None:
    """Losing the channels over-tells; losing the event tells nobody."""
    # Subscribed to nothing: only a broadcast that gave up its channels reaches it.
    socket = await hold(ws_manager, broadcaster, 42)

    await broadcaster.broadcast_to_workspace(
        42,
        "rt_child.updated",
        {"content": "x" * (MAX_PAYLOAD * 2)},
        channels=[f"rt_child:{index}" for index in range(MAX_PAYLOAD // 8)],
    )

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0]["truncated"] is True


async def test_a_worker_hears_the_workspaces_it_holds_and_no_other(broadcaster, ws_manager) -> None:
    """One event costs nothing on the workers that serve none of it."""
    socket = await hold(ws_manager, broadcaster, 42)
    unheld = FakeWebSocket()
    ws_manager.watch(ws_manager.connect(2, unheld), 99)

    await broadcaster.broadcast_to_workspace(99, "rt_record.updated", {"id": 1})
    await asyncio.sleep(0.2)

    assert unheld.sent == []

    await broadcaster.broadcast_to_workspace(42, "rt_record.updated", {"id": 2})

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

    served = await manager.deliver_to_workspace(7, "rt_record.updated", {"id": 1})

    assert served == {2}
    assert len(reading.sent) == 1
    # It is gone, so the next event does not wait on it again.
    assert manager.workspaces() == [7]
    assert 1 not in manager._by_user


async def test_a_socket_leaves_nothing_behind_when_it_goes() -> None:
    manager = local_manager()
    connection = manager.connect(1, FakeWebSocket())

    manager.watch(connection, 7)
    manager.subscribe(connection, ["rt_record", "rt_record:42"])

    change = manager.disconnect(connection)

    assert change.removed == 7
    assert manager.is_idle
    assert manager._by_workspace == {}
    assert manager._by_channel == {}


async def test_an_account_hears_about_itself_and_nobody_else_does(ws_manager, workspace_env, monkeypatch) -> None:
    """Addressed to the person: they belong to several workspaces, and their own
    news is not the business of any of them."""
    to_user = _user_broadcasts(monkeypatch)
    to_workspace = _record_broadcasts(monkeypatch)

    owned = RtOwned(workspace=workspace_env.workspace, user=workspace_env.admin, label="A key")
    await owned.save()

    await wait_until(lambda: bool(to_user))

    assert to_user[0]["user"] == workspace_env.admin.id
    assert to_user[0]["event"] == "rt_owned.created"
    assert to_user[0]["data"] == {"model": "rt_owned", "id": owned.id}
    assert of(to_workspace, "rt_owned") == []


async def test_an_action_can_be_turned_off(ws_manager, workspace_env, monkeypatch) -> None:
    to_user = _user_broadcasts(monkeypatch)

    owned = RtOwned(workspace=workspace_env.workspace, user=workspace_env.admin, label="A key")
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
    """The workspace says who may hear, the channels say who wants to."""
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

    served = await manager.deliver_to_workspace(
        1,
        "rt_record.updated",
        {"model": "rt_record", "id": 42},
        channels=["rt_record", "rt_record:42"],
    )

    assert served == {1, 2}
    assert elsewhere.sent == []


async def test_leaving_a_workspace_drops_what_was_subscribed_there() -> None:
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


async def test_a_write_reaches_a_watching_socket_the_whole_way_through(ws_manager, workspace_env) -> None:
    """The whole chain, on the application's own broadcaster.

    A record is written, the write is announced, it travels through Postgres,
    comes back to this worker and lands in a socket that asked for it. Every
    other test cuts the chain somewhere; this one does not.
    """
    env = workspace_env
    broadcaster = get_service(WebSocketBroadcaster)

    await broadcaster.wait_listening()
    socket = await hold(ws_manager, broadcaster, env.workspace.id, ["rt_record"])

    record = RtRecord(workspace=env.workspace, name="Mem0")
    await record.save()

    assert await wait_until(lambda: bool(socket.sent))
    assert socket.sent[0] == {
        "type": "rt_record.created",
        "data": {"model": "rt_record", "id": record.id},
    }
