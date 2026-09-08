# Realtime

**What one client writes reaches the browsers watching it, on every worker.**

A write made through the API, through the MCP server or by an agent is announced to the
clients reading that data, over a WebSocket. Nothing is polled, and no feature has to
carry its own notification: a model declares that its writes are announced, and every
client watching it hears them.

## Key features

- **Declarative**: `@realtime_model()` on a model, nothing else. Its inserts, updates and
  deletes are announced from the ORM signals, whoever made them.
- **Multi-worker**: an announcement travels through PostgreSQL `LISTEN`/`NOTIFY`, so a
  write served by one worker reaches the sockets held by all the others.
- **Scoped to what is being read**: a worker only hears about the workspaces it holds a
  socket for, and a socket only hears about the records it asked about.
- **Identifiers only**: an event names what moved, never its content. The client reads the
  record back through the API, so the announcement never leaks a field a reader may not see.
- **Committed writes only**: an announcement is published after the transaction commits, so
  a rolled back attempt, or one replayed under `SERIALIZABLE`, announces nothing.
- **Addressed**: to a workspace, or to one account for what belongs to a person rather than
  to a space.

## Quick example

```python
from fastedgy.app import FastEdgy
from fastedgy.api import realtime
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.orm import fields
from fastedgy.realtime import realtime_model


app = FastEdgy(realtime=True)

public_router.include_router(realtime.router)


@realtime_model()
class Company(BaseModel, WorkspaceableMixin):
    name = fields.CharField(max_length=200)
```

Writing a company now announces `company.created`, `company.updated` or `company.deleted`
to every client reading that workspace:

```json
{ "type": "company.created", "data": { "model": "company", "id": 42 } }
```

## Common use cases

- **A list that stays current**: an agent enriching records in the background, a colleague
  editing the same screen.
- **A record open on two screens**: whoever reads one record hears about it alone, not about
  every write of the model.
- **Metadata a client caches**: custom fields declared for a workspace, so a column removed
  disappears without a reload.
- **Something of a person's own**: an API key issued, a notification, addressed to that
  account wherever it is connected.

## Get started

[Getting Started](getting-started.md){ .md-button .md-button--primary }
[Usage Guide](guide.md){ .md-button }
[Technical Details](technical.md){ .md-button }

The Vue.js side, which holds the socket and keeps a view in step with it, is documented in
[Vue.js / Realtime](../../vue/realtime/overview.md).
