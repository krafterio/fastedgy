# Realtime - Usage Guide

Everything a model can declare about what it announces, and to whom.

## Choosing the actions

All three are announced by default. Turn one off by name:

```python
@realtime_model(delete=False)
class Company(BaseModel, WorkspaceableMixin): ...
```

`create`, `update` and `delete` are the names; they reach the client as `company.created`,
`company.updated` and `company.deleted`.

An unknown name is refused at import time rather than silently ignored:

```python
@realtime_model(patch=False)  # ValueError: Unknown realtime actions ['patch']
```

## Carrying a few columns

An event names a record, it does not carry one. `fields` names the columns to carry
**alongside** the identifiers, so a client can tell whether an event is any of its business
without reading the record first:

```python
@realtime_model(fields=["record_model", "record_id"])
class Attachment(BaseModel, WorkspaceableMixin): ...
```

A dict renames on the way out:

```python
@realtime_model(fields={"company_id": "company"})
class Contact(BaseModel, WorkspaceableMixin):
    company = fields.ForeignKey(Company, null=True, related_name="contacts")
```

```json
{ "type": "contact.created", "data": { "model": "contact", "id": 7, "company_id": 42 } }
```

A foreign key gives its id. Nothing is read that the write did not carry, because this runs
on a row being inserted (not yet readable) or on one being deleted.

!!! warning "Keep it to identifiers"
    Whatever is listed here reaches every socket of the scope subscribed to the
    channel, without going back through the API's own field permissions. Carry what
    addresses the event, never its content.

## Reaching the records it hangs off

A page reading one record wants to hear about what hangs off it, without subscribing to
every record of the other model. `relations` names the relations whose own channel the event
also reaches:

```python
@realtime_model(relations=["company"])
class Contact(BaseModel, WorkspaceableMixin):
    company = fields.ForeignKey(Company, null=True, related_name="contacts")
```

Writing a contact of company 42 now reaches `company:42` as well as `contact` and
`contact:7`. The page reading that company hears about it, having subscribed to one channel.

Any relation kind answers:

| Relation | How it is resolved | Cost |
|----------|--------------------|------|
| Foreign key | from the values being written | free |
| Generic foreign key | from the values being written | free |
| Many-to-many, reverse relation | by reading the related rows | one query per write |

The last one is why relations are declared rather than assumed.

A to-many that fans out to more than 50 records announces itself on the model's own channel
alone: naming every related record would make the message larger than a `NOTIFY` carries,
and a list refreshing is what such a write means anyway.

## Addressing the event

### To a scope

By default the event is addressed to the scope held by the `workspace` column, which
[WorkspaceableMixin](../multi-tenant/overview.md#workspaceablemixin) provides. A record with
no scope announces nothing: nobody is watching it.

A model that is a scope itself names its own column:

```python
@realtime_model(scope_field="id")
class Workspace(BaseWorkspace): ...
```

### To an account

What belongs to a person rather than to a space reaches every socket that account holds, and
no one else's, in whichever scope they are reading:

```python
@realtime_model(user_field="id")  # the account itself
class User(BaseUser): ...


@realtime_model(user_field="user")  # something of theirs
class UserApiToken(BaseUserApiToken): ...
```

An account belongs to several scopes, and its own news is not the business of any of them,
which is why this is not just a scope event with a filter. An application can still have such a
write reach other accounts, see [Deciding who hears the rest](#deciding-who-hears-the-rest).

### To the accounts a record reaches

What belongs to several people names the path to them. Each step is a foreign key or a
reverse relation, and the last one names the account:

```python
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.realtime import realtime_model


class Thread(BaseModel):
    name = fields.CharField(max_length=200)


class Member(BaseModel):
    thread = fields.ForeignKey(Thread, on_delete="CASCADE", related_name="members")
    user = fields.ForeignKey("User", on_delete="CASCADE", related_name="memberships")


@realtime_model(user_field="thread.members.user", fields=["thread"], relations=["thread"])
class Message(BaseModel):
    thread = fields.ForeignKey(Thread, on_delete="CASCADE", related_name="messages")
    content = fields.TextField()
```

Writing a message reaches the members of its thread, wherever they are connected, and nobody
else: the people in a thread need not share a scope. The event still travels on `message`,
`message:7` and `thread:3`, which say what it is about and who was
[watching it](#knowing-who-was-watching).

The path is read when the write is made, through the unscoped manager: the first foreign key
comes from the values being written, and each further step costs at most one query. A delete
reads it before the row goes, so the members of a thread being deleted still hear about it
after the cascade has taken their membership away.

## What rides beside the event

Two things are known about a write rather than about the record, and travel on the frame
itself rather than inside `data`:

```json
{
  "type": "company.updated",
  "data": { "model": "company", "id": 42 },
  "changed": ["name", "domain"],
  "origin": "3f2b8c1e-..."
}
```

### `changed`

The columns the write moved, on an update only. A row appearing or going is news to a list
whatever its columns are, so it is absent on a create and a delete.

It is what the server actually wrote, not what a client asked for, so it includes whatever
the model stamps on every write. A view reading none of these columns has nothing to learn
from the event and can leave it alone; see
[`watchFields`](../../vue/realtime/guide.md#only-what-a-view-reads) on the Vue.js side.

### `origin`

Which client instance made the write, read from the `X-Origin-Id` header of the request that
caused it. A client that stamps its writes recognises its own announcement coming back and
leaves it alone, rather than re-reading what it just wrote.

```
X-Origin-Id: 3f2b8c1e-...
```

Absent when the writer did not say, which is the case for an agent writing through the MCP
server or for a queued task. Such a write is announced to everyone, as it should be.

It is a client-supplied string, only ever compared and never trusted, and capped at 64
characters: it travels in a `NOTIFY` payload, where an oversized one would push the
announcement past what PostgreSQL carries and cost it its channels.

The Vue.js fetcher stamps every request with it, so nothing is needed from an application
using `vue-fastedgy`.

## Announcing something of your own

The broadcaster is a service like any other, for what is not a model write:

```python
from fastedgy.dependencies import get_service
from fastedgy.realtime import WebSocketBroadcaster


async def notify_import_finished(scope_id: int, rows: int) -> None:
    broadcaster = get_service(WebSocketBroadcaster)

    await broadcaster.broadcast_to_scope(
        scope_id,
        "import.finished",
        {"rows": rows},
    )
```

Without `channels`, it reaches every socket of the scope. With them, only those
subscribed to one of the names given.

`broadcast_to_user(user_id, event_type, data)` addresses one account instead, and
`broadcast_to_users(user_ids, event_type, data)` several at once.

### Saying what an event is about

An event about a record says so with `about`, and reaches only the members who can read that record
when its model is guarded:

```python
await get_service(WebSocketBroadcaster).broadcast_to_scope(
    scope_id,
    "spot.geofence_changed",
    {"spot_id": spot.id},
    about=(Spot, spot.id),
)
```

A record about to be deleted can no longer be read afterwards: ask who reads it first, and hand them
over with `audience`.

```python
from fastedgy.realtime.access import readers

audience = await readers(Spot, spot.id, scope_id)
await spot.delete()
await broadcaster.broadcast_to_scope(scope_id, "spot.geofence_changed", {"spot_id": spot.id}, audience=audience)
```

### Deciding who hears the rest

Every event published to a scope goes through `RealtimeAuth.audience` on the worker that delivers it,
and every write addressed to accounts through `RealtimeAuth.recipients`, with the accounts its
`user_field` names. An application replaces the service to narrow its own events, or to have a write
reach accounts its path does not name:

```python
from typing import Any

from fastedgy.dependencies import register_service
from fastedgy.realtime import RealtimeAuth


async def members_sharing_their_location(scope_id: int, user_ids: set[int]) -> set[int]: ...


async def support_agents() -> set[int]: ...


class AppRealtimeAuth(RealtimeAuth):
    async def audience(self, scope_id: int, event_type: str, data: Any, user_ids: set[int], about: Any = None) -> Any:
        if event_type.startswith("location."):
            return await members_sharing_their_location(scope_id, user_ids)

        return await super().audience(scope_id, event_type, data, user_ids, about)

    async def recipients(self, event_type: str, data: Any, user_ids: set[int]) -> Any:
        if data["model"] == "ticket_message":
            return user_ids | await support_agents()

        return await super().recipients(event_type, data, user_ids)


register_service(AppRealtimeAuth, key=RealtimeAuth, force=True)
```

`audience` runs on the delivery path: keep it short, and read in one go what it needs. `recipients` is
asked once per write, by the process that writes: before the row goes for a deletion, once the write is
committed otherwise.

!!! note "Yours are yours"
    An event you publish yourself carries no `origin`, so it is never taken for an echo and
    is delivered to its author too. On the Vue.js side it arrives on the bus under its own
    name rather than as a resource change.

### Leaving someone out

`exclude_user_ids` keeps a scope event from the sockets of these accounts, which is how
the author of an event is left out of it:

```python
from fastedgy.dependencies import get_service
from fastedgy.realtime import WebSocketBroadcaster


async def ask_for_presence(scope_id: int, asker_id: int) -> None:
    await get_service(WebSocketBroadcaster).broadcast_to_scope(
        scope_id,
        "presence.requested",
        {"asker": asker_id},
        exclude_user_ids=[asker_id],
    )
```

## Knowing who was watching

Some writes mean something to the people looking at them: a message is read by whoever has
its thread open. A worker that delivers an event carrying channels tells the bus which of the
accounts it reached had subscribed to one of them, as `OnRealtimeDeliveredEvent`:

```python
from fastedgy.bus import on_event
from fastedgy.realtime import OnRealtimeDeliveredEvent


async def mark_read(message_id: int, user_ids: list[int]) -> None: ...


@on_event(OnRealtimeDeliveredEvent)
async def mark_read_by_watchers(event: OnRealtimeDeliveredEvent) -> None:
    if event.event_type != "message.created":
        return

    channel = f"thread:{event.data['thread']}"
    readers = [user_id for user_id, channels in event.watchers.items() if channel in channels]

    if readers:
        await mark_read(event.data["id"], readers)
```

`watchers` maps an account to the channels of the event its sockets had subscribed to, on
that worker. It is dispatched only when a listener is registered, and only when somebody was
watching.

It runs on the delivery path of the worker holding the sockets, where no request context is
set: keep it short, and hand anything slow to a queued task.

## Frames of your own

The socket takes `watch`, `subscribe`, `unsubscribe` and `heartbeat` for itself. Any other
frame an authenticated client sends goes to the bus as `OnRealtimeFrameEvent`, and the end of
the socket as `OnRealtimeDisconnectEvent`:

```python
from fastedgy.bus import on_event
from fastedgy.realtime import OnRealtimeDisconnectEvent, OnRealtimeFrameEvent


async def release(user_id: int, record_ids: set[int]) -> None: ...


@on_event(OnRealtimeFrameEvent)
async def on_presence(event: OnRealtimeFrameEvent) -> None:
    if event.event_type == "presence.open":
        event.connection.state.setdefault("open", set()).add(event.data["record"])


@on_event(OnRealtimeDisconnectEvent)
async def on_gone(event: OnRealtimeDisconnectEvent) -> None:
    if event.connection.state.get("open"):
        await release(event.connection.user_id, event.connection.state["open"])
```

`event.connection` is the socket: its account, the scope it reads, its subscriptions,
and `state`, a dict for what an application keeps while that socket lives. A frame is handled
before the next one is read, so a slow handler holds up its own socket and no other.

## Who may listen

A socket authenticates itself with its first frame, and the bearer resolves exactly like an
HTTP one: a session JWT or a personal API key both answer. An agent connected with a
`fet_...` key opens a socket where it opens a route, and hears what it writes.

The scope is then checked against the membership of that account, the way an HTTP route
checks it. A client that knows a slug it is not a member of is refused.

Both are checked again while the socket stays open, every `realtime_recheck_interval` seconds: a
socket whose token expired or was revoked is refused, and one whose account left the scope stops
hearing it. See [Technical Details](technical.md#what-a-socket-was-let-in-with-checked-again).

A model whose records not every member may read, through a global filter or an access guard,
announces each of them to the members who can read it, and to no one else. A record shared with other
scopes through a workspace-shareable root reaches its readers there too. See
[Technical Details](technical.md#records-only-some-members-can-read).

A client can only subscribe to a channel of a **registered** model: a name it invents is
dropped rather than honoured.

Both resolutions belong to a service, `RealtimeAuth`, which an application replaces when it
reads them another way. One that resolves the scope of a request itself, rather than from
its URL, answers the same for a socket that names none:

```python
from typing import Any

from fastedgy.dependencies import register_service
from fastedgy.realtime import RealtimeAuth


async def default_scope_of(user: Any) -> Any: ...


class AppRealtimeAuth(RealtimeAuth):
    async def scope_of(self, user: Any, scope: Any) -> Any:
        if scope:
            return await super().scope_of(user, scope)

        return await default_scope_of(user)


register_service(AppRealtimeAuth, key=RealtimeAuth, force=True)
```

Both methods also answer the checks made while a socket stays open: keep them to reading.

## Next steps

[Technical Details](technical.md){ .md-button .md-button--primary }
[Vue.js Realtime](../../vue/realtime/guide.md){ .md-button }
