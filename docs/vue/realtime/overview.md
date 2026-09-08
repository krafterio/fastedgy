# Realtime

**One stream for what changed, wherever the change came from**

A record moves for three reasons: this tab wrote it, another tab or another person wrote it,
or an agent did. `vue-fastedgy` makes all three the same event, so a view says once what it
reads instead of wiring a refresh for its own mutations and another for everyone else's.

## Key features

- **One vocabulary**: `resource:changed` fires whether the write was made here or announced
  by the server. Nothing to wire twice.
- **No echo**: a write made here says so immediately; the server's announcement of that same
  write is recognised and dropped, so a view refreshes once.
- **Works with the socket down**: the local half of the stream is the API layer itself, so a
  view still reacts to its own writes when the connection is gone.
- **Reactive holders**: `useApiRecord` and `useApiCollection` own the re-read, the debounce,
  the local removal on delete and the reconnection.
- **Only what a view reads**: an update that moved nothing a list shows does not make it read
  again.
- **Automatic subscription**: what a view watches is subscribed on the socket while it is on
  screen, and let go when it leaves.

## Quick example

```javascript
import { useRealtime, useApiCollection, useApiRecord } from 'vue-fastedgy';

// Once, in the application shell: hold the socket
useRealtime();

// A list that keeps itself current
const { items, total, status } = useApiCollection('company', () => ({
    fields: 'id,name,domain',
    limit: 25,
}));

// A page reading one record, which closes itself when it is deleted elsewhere
const { data: company, isDeleted } = useApiRecord('company', () => route.params.id);
```

Or, when a view already owns its own loading:

```javascript
import { useResourceChanged } from 'vue-fastedgy';

useResourceChanged('company', () => reload());
```

## How the two halves meet

```
useApiModel('company').update(42, {...})
  ├─ PATCH /api/{workspace}/companies/42     (stamped X-Origin-Id)
  └─ resource:changed                        ← immediately, locally

server announces company.updated
  └─ socket receives it
       ├─ origin is ours   → dropped, this instance already said so
       └─ origin is theirs → resource:changed
```

## Get started

[User Guide](guide.md){ .md-button .md-button--primary }

The server side, which decides what is announced and to whom, is documented in
[Features / Realtime](../../features/realtime/overview.md).
