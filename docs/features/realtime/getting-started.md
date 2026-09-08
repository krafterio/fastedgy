# Getting Started with Realtime

Three steps: turn it on, mount the endpoint, and say which models announce their writes.

## Step 1: Turn it on

```python
from fastedgy.app import FastEdgy

app = FastEdgy(realtime=True)
```

Off by default: it costs a `LISTEN` connection and a pool of consumers per worker, which an
application with nothing to announce should not pay. Turned on, the two services are
registered and the bridge between workers is started and stopped with the application.
Nothing else to wire in a lifespan.

!!! note "PostgreSQL only"
    Announcements travel through `LISTEN`/`NOTIFY`, so realtime needs PostgreSQL.

## Step 2: Mount the endpoint

The socket route is mounted like any other FastEdgy router, on whichever public router the
application builds:

```python
from fastapi import APIRouter
from fastedgy.api import realtime

public_router = APIRouter(prefix="/api")
public_router.include_router(realtime.router)

app.include_router(public_router)
```

It belongs on a **public** router, not behind an authentication dependency: a browser
cannot set an `Authorization` header on a WebSocket handshake, so the socket authenticates
itself with its own first frame.

## Step 3: Declare the models that announce

Nothing is announced by default. An event nobody is watching for is a `NOTIFY`, a wake-up on
every worker holding that workspace and a frame on every socket of it, so a model says so
for itself:

```python
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.orm import fields
from fastedgy.realtime import realtime_model


@realtime_model()
class Company(BaseModel, WorkspaceableMixin):
    name = fields.CharField(max_length=200)
    domain = fields.CharField(max_length=200, null=True)
```

Every insert, update and delete of a company is now announced to the clients reading its
workspace, whoever made it: a browser, an agent through the MCP server, a queued task.

## What a client receives

Two channels carry each write, and a client subscribes to the one it needs:

| Channel | Who subscribes | What it hears |
|---------|----------------|---------------|
| `company` | a list of companies | every write of the model |
| `company:42` | the page reading company 42 | writes on that record |

The frame names what moved:

```json
{
  "type": "company.updated",
  "data": { "model": "company", "id": 42 },
  "changed": ["name"]
}
```

Only identifiers travel. The client reads the record back through the API, which is what
keeps an announcement from carrying a field its reader is not allowed to see.

## Step 4: Connect a client

In a Vue.js application, one call in the shell holds the socket, and one call per view says
what it reads:

```javascript
import { useRealtime, useResourceChanged } from 'vue-fastedgy';

// Once, in the application shell
useRealtime();

// In a view
useResourceChanged('company', () => reload());
```

See [Vue.js / Realtime](../../vue/realtime/guide.md) for the composables, and
[Technical Details](technical.md#the-socket-protocol) for the raw protocol if you connect
from something else.

## Next steps

[Usage Guide](guide.md){ .md-button .md-button--primary }
[Technical Details](technical.md){ .md-button }
