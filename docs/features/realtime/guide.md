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
    Whatever is listed here reaches every socket of the workspace subscribed to the
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

### To a workspace

By default the event is addressed by the `workspace` column, which
[WorkspaceableMixin](../multi-tenant/overview.md#workspaceablemixin) provides. A record with
no workspace announces nothing: nobody is watching it.

A model that is its own tenant names its own column:

```python
@realtime_model(workspace_field="id")
class Workspace(BaseWorkspace): ...
```

### To an account

What belongs to a person rather than to a space reaches every socket that account holds, and
no one else's, in whichever workspace they are reading:

```python
@realtime_model(user_field="id")  # the account itself
class User(BaseUser): ...


@realtime_model(user_field="user")  # something of theirs
class UserApiToken(BaseUserApiToken): ...
```

An account belongs to several workspaces, and its own news is not the business of any of
them, which is why this is not just a workspace event with a filter.

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


async def notify_import_finished(workspace_id: int, rows: int) -> None:
    broadcaster = get_service(WebSocketBroadcaster)

    await broadcaster.broadcast_to_workspace(
        workspace_id,
        "import.finished",
        {"rows": rows},
    )
```

Without `channels`, it reaches every socket of the workspace. With them, only those
subscribed to one of the names given.

`broadcast_to_user(user_id, event_type, data)` addresses one account instead.

!!! note "Yours are yours"
    An event you publish yourself carries no `origin`, so it is never taken for an echo and
    is delivered to its author too. On the Vue.js side it arrives on the bus under its own
    name rather than as a resource change.

## Who may listen

A socket authenticates itself with its first frame, and the bearer resolves exactly like an
HTTP one: a session JWT or a personal API key both answer. An agent connected with a
`fet_...` key opens a socket where it opens a route, and hears what it writes.

The workspace is then checked against the membership of that account, the way an HTTP route
checks it. A client that knows a slug it is not a member of is refused.

A client can only subscribe to a channel of a **registered** model: a name it invents is
dropped rather than honoured.

## Next steps

[Technical Details](technical.md){ .md-button .md-button--primary }
[Vue.js Realtime](../../vue/realtime/guide.md){ .md-button }
