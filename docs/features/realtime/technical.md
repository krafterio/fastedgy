# Realtime - Technical Details

How an announcement travels, and what it costs.

## The problem

A socket is held by one worker process. The write it must announce is made in whichever
worker served the request, which is rarely the same one. Without a bridge, an agent writing
through worker 3 is invisible to a browser connected to worker 1.

## The path of an announcement

```
Model write (worker 3)
  └─ post_save / post_update / pre_delete signal
       └─ read the scope or the accounts, the extra columns,
          the relation channels                                          (in the transaction)
       └─ defer the publication                                          (after commit)
            └─ pg_notify('fastedgy_realtime_<scope id>', payload)
                 └─ every worker LISTENing on that scope
                      └─ WebSocketManager: the local sockets subscribed to a named channel
                           └─ frame
```

Three services do the work, all registered by `FastEdgy(realtime=True)`:

**`WebSocketManager`** holds the sockets of *this* process and delivers to them. It is
deliberately local: it indexes connections by what delivery looks them up by, the scope and
the channel, so an event costs what it delivers rather than what the process happens to hold.

**`WebSocketBroadcaster`** is the bridge. It holds one `LISTEN` connection, publishes with
`pg_notify`, and hands what comes back to the manager.

**`RealtimeAuth`** says who a socket is, from the bearer of its first frame, and which scope
it reads, from the slug it names.

## Only the scopes a worker serves

A worker listens on `fastedgy_realtime` for what belongs to no scope, plus one channel per
scope it actually holds a socket for. The endpoint says so as sockets come and go: taking the
first socket of a scope issues a `LISTEN`, dropping the last one a `UNLISTEN`.

This is what keeps one event from costing something on every worker of the fleet. A worker
holding nothing for an event is never woken by it at all.

A worker starts listening with the first socket it takes, before telling that socket it is
authenticated, and stops with the application. A process that never takes one, a queue
worker, a scheduler or a command, never opens the `LISTEN` connection, and publishes all the
same: `pg_notify` needs nobody listening in the process that calls it.

A supervisor reconciles every 15 seconds: it restarts a listener or a consumer that died, and
brings what the process listens to back in line with what it actually holds. A worker deaf to
a scope it serves would say nothing about it, which is the failure nobody would notice.

## Addressed to accounts

An event addressed to accounts goes out on `fastedgy_realtime`, which every listening worker
hears, in payloads of at most 200 accounts. It reaches every socket of those accounts,
whatever scope each one reads: its channels do not narrow it, they say what it is about.

For a write of a model declared with `user_field`, the accounts are the ones its path names, as
`RealtimeAuth.recipients(event_type, data, user_ids)` returns them: unchanged by default, and an
application replaces the service to add or remove accounts. The process that writes asks it, before
the row goes for a deletion, once the write is committed otherwise. When it fails, the write is
announced to nobody.

A worker that delivers an event carrying channels, to accounts or to a scope, then tells
the bus which of the accounts it reached had subscribed to one of them
(`OnRealtimeDeliveredEvent`), when a listener asks.

## Records only some members can read

A model with a global filter or an access guard reads narrower than its scope: a member may be
refused one of its records. What is announced about such a record reaches only the members who
can read it, each asked the way a request of theirs would ask, as that account, in that scope,
through the model's scoped manager:

- a creation or an update is checked by the worker delivering it, for the accounts it holds a
  subscribed socket for;
- a deletion is checked by the process that deletes, before the row goes, for every member of the
  scope, and travels with the accounts it may reach.

Each account's question is built in Python, as that account, and all of them are put to the database
together, in a single `SELECT EXISTS (...), EXISTS (...)`: two queries per event, the memberships and
that one, however many accounts are asked.

The check belongs to `RealtimeAuth.audience(scope_id, event_type, data, user_ids, about)`, which the
delivering worker calls for every event published to a scope. By default an event about a record of a
guarded model reaches that record's readers, and any other event every account asked. An application
replaces the service to narrow its own events; `broadcast_to_scope` names the record an event is about
with `about`, and hands over readers asked beforehand with `audience`.

## Records shared with other scopes

A record under a workspace-shareable root, a task of a shared project for one, is read too by the
root's members from their own scope. What is announced about it also reaches those members outside its
scope, each asked the way the shared-record context asks: the root's `workspace_shareable_authorize`,
then the record, read as the root's workspace with the confinement filters armed. They hear it on every
socket they hold. A deletion asks before the row goes, like any other.

## Committed writes only

The announcement is prepared in the write's own transaction and published after it commits,
through [`run_signal_side_effect`](../../features/orm-extensions/overview.md).

This matters more than it looks. FastEdgy's default isolation is `SERIALIZABLE` with replay:
announcing from inside the transaction told clients about a write that had not happened, and
told them once per attempt when one was replayed.

What the announcement needs from the row is read **before** the commit, and for a delete before
the row goes, from the `pre_delete` signal: a deleted record has lost its links by the time the
announcement goes out, and a database cascade takes the related rows with it. Only the
publication itself is deferred, and a delete is published from `post_delete`, once its row is gone:
a client reading the record again as soon as it hears must not find it still there.

An announcement that fails never fails the write it announces. It is logged and dropped.

## When a payload is too large

PostgreSQL refuses a `NOTIFY` payload of 8000 bytes outright, and the event would be lost for
everyone. So it goes out with less rather than not at all, in two steps:

1. **Without its data**, but for the `model` and the `id` that name a record, marked
   `truncated`, which tells the client to read the record for itself rather than trust what it
   holds.
2. **Without the channels that narrow it**, if that is still too much, which serves the whole
   scope instead of exactly the sockets that asked.

Over-telling beats a silence nothing recovers from.

A date travels in ISO 8601, the way the API writes it.

## Holding the LISTEN connection

The connection sits idle between announcements, and an idle flow is what a container overlay
network evicts: a Docker Swarm overlay (IPVS/conntrack) drops it after a few minutes, leaving
a half-open socket that delivers nothing and says nothing.

Two guards, both configurable:

- an application-level probe every 30 seconds, well inside that window, which keeps the flow
  warm and surfaces a dead connection so it can be re-established;
- TCP keepalive on the socket, the Linux default idle of two hours being far longer than an
  overlay's patience.

Reconnection backs off exponentially. The log level follows the divergence rather than the
count: a blip that heals in a couple of attempts is a warning, but a connection that cannot
come back **while the database answers** is an error, that being the pathology the supervisor
exists for.

## Delivery to a socket

Frames go out to all the targets of an event at once, not one after another: a socket that has
stopped reading would otherwise hold the event back from everyone behind it in the loop.

One that cannot take a frame within 5 seconds is not reading. It is dropped there and then, and
closed with code 1011, which lets it reconnect and lets everyone else hear the event now.

## What a socket was let in with, checked again

A socket is authenticated once, by its first frame, and what let it in can stop holding while it stays
open: a token expires, an API key is revoked, an account is deleted, a membership ends. Every
`realtime_recheck_interval` seconds, each socket resolves its bearer and its scope again, through
`RealtimeAuth`, the way its first frame was resolved:

- a bearer that no longer stands for the account is refused with `Invalid authentication token`, and
  the socket closed with code 1008. The client authenticates again with what it holds now:
  `vue-fastedgy` and `flutter_fastedgy` both refresh their token first.
- a scope the account lost is left, with what the socket subscribed to there. The socket stays, for
  what is addressed to the account itself.

Deleting or changing a membership or a personal API key, deleting an account, or changing the email
or username its session tokens name has the sockets of that account checked at once, on every
worker. A write no ORM signal sees, a cascade in the database or a queryset write, waits for the next
round. `WebSocketBroadcaster.recheck_users(user_ids)` asks for the same check from anywhere else.

## The socket protocol

The contract any client is written against, `vue-fastedgy` and `flutter_fastedgy` included.
Everything is JSON,
`{"type": ..., "data": {...}}`. The socket is not in the OpenAPI document, which describes HTTP
routes only: this section is its specification.

### Client to server

| Type | Data | Meaning |
|------|------|---------|
| `authenticate` | `{token, scope}` | **First frame, required.** A session access JWT or a personal API key, and the slug of the scope being read, or `null`. |
| `watch` | `{scope}` | The client now reads another scope. The subscriptions made on the one it leaves are dropped. |
| `subscribe` | `{channels: [...]}` | Hear about these. `company` for a list, `company:42` for a record. |
| `unsubscribe` | `{channels: [...]}` | Stop hearing about these. |
| `heartbeat` | | Ignored, for a client that wants to keep the flow warm. |

A browser cannot set headers on a WebSocket handshake, which is why the bearer arrives as the
first frame. An unauthenticated socket is held open for 30 seconds and then closed.

What the table does not say:

- `subscribe` and `unsubscribe` also take a single `{channel: "company"}`.
- A channel whose model is not declared with `@realtime_model` is dropped without a word, so a
  client subscribes without knowing which models announce.
- `authenticate` refuses a scope the account is not a member of. `watch` does not refuse it: the
  socket is left on no scope at all.
- A `watch` that moves to another scope drops every subscription, and a subscription made on no
  scope reaches nothing addressed to a scope until then. A client says its channels again after
  each `watch` it sends and after each `auth_success`. A `watch` naming the scope already read
  changes nothing.
- A frame that is not a JSON object closes the socket, and a `data` that is not an object is read as
  empty. Any other type goes to the application, on the bus (`OnRealtimeFrameEvent`).
- A socket holds at most `realtime_max_channels` channels: what it asks for past that is ignored. A
  frame heavier than `realtime_max_frame_size` closes the socket with code 1009, and more than
  `realtime_frame_limit` frames in ten seconds with code 1008.
- An account holds at most `realtime_max_sockets_per_user` sockets on a worker: one more is refused
  with `Too many connections`. A `watch` naming the scope the socket already reads is ignored.

### Server to client

| Type | Meaning |
|------|---------|
| `auth_success` | `{user_id, scope}`. The socket may stay. |
| `auth_error` | `{message}`, followed by a close with code 1008. |
| `<model>.<action>` | A record moved. `data` is `{model, id, ...declared fields}`, with `changed`, `origin` and `truncated` beside it. |
| anything else | Whatever the application published for itself. |

A refusal names its reason: `Authentication timeout`, `Invalid authentication format`, `Invalid
authentication message`, `Invalid authentication token`, `Scope not found`, `Too many connections`. None of them fixes
itself, so a client does not send the same frame again. A refused token is the one a client can cure,
by refreshing it before it authenticates again.

An event travels on the channels of its record and of the records it hangs off, but the frame does
not say which channel carried it: a client dispatches it by the model it names. A
`contact.created` reaching a client whose only subscription is `company:42` is still a `contact`
event.

### Recognising its own writes

A request carries `X-Origin-Id`, and every announcement it causes carries the value back as
`origin`, a signal's writes included. A client that stamps a write with an origin of its own,
`<instance>.<n>`, and remembers the record that write names, drops the one frame that echoes it
and hears the rest: what a signal wrote on another record while serving the request is news to
the writer too. `vue-fastedgy` does so for the writes of `useApiModel`, `flutter_fastedgy` for
those of `ApiModel`.

### A native client

| | Browser (`vue-fastedgy`) | Native (`flutter_fastedgy`) |
|-|--------------------------|-----------------------------|
| Liveness | a `heartbeat` frame every 30 seconds | a WebSocket ping every 30 seconds, which the server answers; a missing pong closes the socket |
| Handshake headers | none of its own | `User-Agent` |
| Token | refreshed first when expired, and when the server refuses it | validated again at every opening, and refreshed when the server refuses it |
| In the background | the tab keeps its socket | closed after 20 seconds, opened again on resume |
| Network change | the browser reports the close | connectivity coming back opens it at once |

A ping rather than a `heartbeat` frame keeps an idle flow warm the same way, and also detects a
socket that died without a close, which is what a phone switching networks leaves behind.

The socket changes nothing in the database for itself. Reads are what the rest of the API is
for, and a frame of the application's own is the application's to handle.

Nothing is replayed. Whatever happened while a socket was down was said to nobody, so a client
coming back must read again rather than keep showing what it held.

## Settings

All under `realtime_`, on `BaseSettings`, so a deployment says so in its own `.env`.

| Setting | Default | What it is |
|---------|---------|------------|
| `realtime_channel` | `fastedgy_realtime` | The PostgreSQL channel base name. Each scope gets `<channel>_<id>`. |
| `realtime_auth_timeout` | `30.0` | Seconds an unauthenticated socket is held open. |
| `realtime_send_timeout` | `5.0` | Seconds one socket may hold up an event before it is dropped. |
| `realtime_recheck_interval` | `60.0` | Seconds between two checks of what a socket was let in with, its bearer and its scope. |
| `realtime_max_channels` | `1000` | Channels one socket may hold. |
| `realtime_max_frame_size` | `65536` | Characters a client frame may hold. |
| `realtime_frame_limit` | `200` | Frames a socket may send in any ten seconds. |
| `realtime_max_sockets_per_user` | `20` | Sockets one account may hold on a worker. |
| `realtime_consumer_pool_size` | `4` | Concurrent consumers draining the notify queue. |
| `realtime_notify_queue_size` | `10000` | Payloads a worker may hold before dropping them. |
| `realtime_heartbeat_interval` | `30.0` | Seconds between probes on the `LISTEN` connection. Lower it on a network less patient than that. |
| `realtime_heartbeat_timeout` | `10.0` | Seconds to wait for a probe before treating the connection as dead. |
| `realtime_reconnect_backoff_start` | `1.0` | First delay before re-establishing `LISTEN`. |
| `realtime_reconnect_backoff_max` | `30.0` | Cap the exponential backoff climbs to. |
| `realtime_supervise_interval` | `15.0` | Seconds between the supervisor's checks. |
| `realtime_tcp_keepidle` | `30` | TCP keepalive idle, in seconds, on the `LISTEN` socket. |
| `realtime_tcp_keepintvl` | `10` | Seconds between TCP keepalive probes. |
| `realtime_tcp_keepcnt` | `3` | Failed probes before the socket is dropped. |

## What it costs

| | Cost |
|-|------|
| A process that never took a socket | Nothing: it never opens the `LISTEN` connection. |
| A worker holding sockets | One `LISTEN` connection, four consumer tasks, one supervisor task. |
| An open socket | Its bearer and its scope resolved again every `realtime_recheck_interval` seconds, a query or two each. |
| A write on a guarded model | Two queries: the memberships, and one statement asking every account at once. |
| A write under a shared root | The root, its members, and one statement asking those outside the scope. |
| A worker whose sockets are all gone | An announcement it does not listen for never reaches it; one that does is dropped before it is parsed. |
| A model without `@realtime_model` | Nothing, no signal is connected. |
| A model with it, `realtime=False` | Nothing: the announcement stops before a broadcaster is brought into being. |
| One write | One `pg_notify` per 200 accounts addressed, plus one query per declared to-many relation and at most one per further step of a `user_field` path. |

## Testing

`WebSocketBroadcaster` takes its settings by constructor injection, so a test builds one on a
channel of its own with timings it can wait on, while still going through the real round-trip:

```python
import pytest

from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.orm import Database
from fastedgy.realtime import WebSocketBroadcaster, WebSocketManager


@pytest.fixture
async def broadcaster(setup_db):
    instance = WebSocketBroadcaster(
        get_service(BaseSettings).model_copy(
            update={
                "realtime_channel": "ws_test",
                "realtime_heartbeat_interval": 0.2,
                "realtime_supervise_interval": 0.1,
            }
        ),
        get_service(Database),
        get_service(WebSocketManager),
    )
    await instance.ensure_listening()

    yield instance

    await instance.stop()
```

The application's own broadcaster listens once a socket arrives: a test that drives it without
going through the endpoint calls `await get_service(WebSocketBroadcaster).ensure_listening()`
first.

The HTTP test client cannot speak WebSocket, so a fake socket with a `send_json` method is
what `WebSocketManager.connect()` is given.

Remember that publication is **asynchronous**: it happens after the transaction commits, in a
task of its own, so it is never done by the time the write returns. Wait for the announcement
rather than asserting straight after the write.
