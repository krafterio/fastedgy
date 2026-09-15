# Realtime - User Guide

## Holding the socket

One call, in the application shell, and nowhere else:

```vue
<script setup>
import { useRealtime } from 'vue-fastedgy';

useRealtime();
</script>
```

It opens the socket when an account is signed in, points it at the scope being read, and closes
it on sign-out. `useRealtime()` takes no argument: whatever knows the scope announces it on the
bus under `REALTIME_SOURCE`, as a ref or a getter the socket follows. `useWorkspaceStore()` does
so for itself, so an application built on it has nothing to write.

A page with no scope (an onboarding, an auth screen) still opens the socket, on no scope: what is
addressed to the account reaches it, and the scope is told to the server once one is named.

An application that names its scope another way announces its own source, from the application
shell:

```javascript
import { useRoute } from 'vue-router';
import { bus, REALTIME_SOURCE } from 'vue-fastedgy';

const route = useRoute();

bus.trigger(REALTIME_SOURCE, { source: () => route.params.scope ?? null });
```

A closed socket is reopened, later each time up to 30 seconds, so a tab left open through a
deploy or a laptop coming out of sleep finds its way back without hammering the server.

The server checks the token again while the socket is open. One it refuses, expired or revoked, is
refreshed once, and the socket opens again with the new one.

## Holding a record

```vue
<script setup>
import { useRoute } from 'vue-router';
import { useApiRecord } from 'vue-fastedgy';

const route = useRoute();
const { data: company, status, error, isDeleted, refresh } = useApiRecord(
    'company',
    () => route.params.id,
    { fields: 'id,name,domain,category.name' },
);
</script>

<template>
  <Skeleton v-if="status === 'loading'" />
  <EmptyState v-else-if="isDeleted" />
  <CompanyCard v-else-if="company" :company="company" />
</template>
```

| Returned | |
|----------|-|
| `data` | The record, or `null` before the first read and after it is deleted. |
| `status` | `idle` / `loading` / `success` / `error`. |
| `error` | The failure of a read the user asked for. A silent refresh that fails leaves it alone. |
| `isDeleted` | `true` once the record was deleted anywhere, or a silent re-read finds it gone. The screen can close itself. |
| `refresh()` | Read again, with the loading state. |

It re-reads itself **silently** when the record is updated anywhere, keeping the previous
value until the new one arrives so a refresh never blanks the screen. The `id` may be a plain
value, a ref or a getter, and the holder follows it.

## Holding a list

```javascript
import { useApiCollection } from 'vue-fastedgy';

const { items, total, status, error, refresh } = useApiCollection('company', () => ({
    fields: 'id,name,domain',
    filter: search.value ? ['name', 'icontains', search.value] : undefined,
    limit: 25,
}));
```

Pass the query as a getter or a ref and the list re-reads when it changes.

Three things it does that a hand-rolled refresh usually does not:

- **A delete drops its row** without going back to the server.
- **A burst is collapsed**: a field saved on a timer fires one event per tick, and re-reading
  on each of them is a request per keystroke settled. 250 ms by default, `refreshDelay` to
  change it.
- **An update that moved nothing it reads is ignored**, see below.

### Only what a view reads

The columns a list asks for say what it depends on. An update that moved none of them is news
to somebody else:

```javascript
// Depends on what it reads: name and domain
useApiCollection('company', () => ({ fields: 'id,name,domain' }));
```

A list that reads more than it depends on says so:

```javascript
useApiCollection('company', () => ({ fields: 'id,name,domain,internal_note' }), {
    watchFields: ['name', 'domain'],
});
```

A create or a delete always counts: a row appearing or going changes a list whatever its
columns are. And an update that did not say what it moved counts too, an event that says
nothing meaning everything.

A custom field counts for the column that stores it. The server announces an update of `extra`,
which reaches a view reading `extra_priority`, and a write of `extra_priority` reaches a view
reading `extra`. Two different custom fields do not touch.

## Holding a record's neighbours

A detail screen opened from a list steps to the previous and the next record of that list. It
hands the filter and the ordering of the list to the holder, which asks the model's
[`siblings` route](../../features/api-routes/guide.md#record-siblings), opt-in on the server:

```javascript
import { useApiSiblings } from 'vue-fastedgy';

const { previous, next, status } = useApiSiblings('company', () => route.params.id, () => ({
    filter: ['country', '=', 'FR'],
    orderBy: 'name:asc',
}));
```

It follows the id and the query, keeping only the answer of the last id asked when steps
outrun the server, and re-reads after a write on the model anywhere, a burst collapsed like a
list's. The previous neighbours stay until the new ones arrive: a pager disables itself while
`status` is `loading`.

## Listening without holding

A view that already owns its loading uses the primitive the holders are built on:

```javascript
import { useResourceChanged } from 'vue-fastedgy';

// A list that refreshes on any write of the model
useResourceChanged('company', () => reload());

// A page that follows the record it reads
useResourceChanged('company', () => load(), { id: () => route.params.id });

// A list that only cares about the columns it shows
useResourceChanged('company', () => reload(), { watchFields: ['name', 'domain'] });

// Straight away, no collapsing
useResourceChanged('company', (change) => apply(change), { refreshDelay: 0 });
```

The handler receives what is known about the change:

```javascript
{ model: 'company', id: 42, action: 'updated', changed: ['name'], origin: null, truncated: false, announced: true }
```

Events carry identifiers only: read the record back through the API rather than trusting
`changed` to tell you the new value.

### Reconnection

The handler is also called with `action: 'reconnected'` and no id when the socket comes back:

```javascript
useResourceChanged('company', ({ action }) => {
    // 'created' | 'updated' | 'deleted' | 'reconnected' | 'stale'
    reload();
});
```

Nothing is replayed. What happened while the socket was down was said to nobody, so the view
has to read again to stop showing a stale screen. That call is never held back by the
debounce. The holders do this for you.

### A tab in the background

While the document is hidden, the handler is not called. What came meanwhile, a reconnection
included, is owed as one call when the tab shows again:

```javascript
{ model: 'company', id: null, action: 'stale', changed: null, origin: null, truncated: true, data: null }
```

A read a view had already scheduled when the tab hid still happens. `useRealtimeEvent` is never
held: an application's own event is for the application to judge.

## Your own writes

Nothing to declare. `useApiModel` announces its own mutations:

```javascript
import { useApiModel } from 'vue-fastedgy';

const api = useApiModel('company');

await api.update(42, { name: 'Krafter SAS' });
// → resource:changed { model: 'company', id: 42, action: 'updated', changed: ['name'] }
```

Every holder and every `useResourceChanged` watching `company` reacts, in this tab, straight
away, whether or not the socket is connected.

### Why it does not fire twice

Every request is stamped with an `X-Origin-Id` naming this instance of the application, for
the life of this page, and a write of `useApiModel` stamps an origin of its own,
`<originId>.<n>`. The server hands it back on every announcement that request caused, and the
socket drops the one frame about the record the local event already named.

Everything else is delivered: what a signal wrote on another record while serving the request,
posting a message subscribing its author for one, and a write through `action()` or a route of
your own. Such a frame carries `origin: originId` and `announced: true`, so a view that skips
its own writes with `origin === originId` still does, and one that wants to tell a local event
from an announcement tests `announced`.

An announcement with no origin, or with somebody else's, is delivered normally. An agent
writing through the MCP server sends none, so its writes always reach every client.

Nothing to configure: `createFetcher` installs the stamping.

## Events of your own

Whatever the server publishes under a name of its own arrives on the [bus](../bus/overview.md)
under that name, not as a resource change:

```javascript
import { bus, useBus } from 'vue-fastedgy';

useBus(bus, 'import.finished', (event) => {
    console.log(event.detail.data.rows);
});
```

Only `created`, `updated` and `deleted` become a resource change. `import.finished` is your
event, and is never mistaken for a write on a model called `import`.

Such an event carries no origin, so it is never taken for an echo: you hear your own.

A view hears one while it is on screen with `useRealtimeEvent`, whose handler gets the payload
and what rides beside it:

```javascript
import { useRealtimeEvent } from 'vue-fastedgy';

useRealtimeEvent('import.finished', (data, { truncated }) => {
    if (truncated) {
        reload();

        return;
    }

    console.log(data.rows);
});
```

`truncated` says the server left the payload behind, over what a `NOTIFY` carries: read what
the event was about back through the API.

## Testing a view

Give a holder its own reader and drive it with the change event:

```javascript
import { flushPromises, mount } from '@vue/test-utils';
import { notifyChanged, useApiCollection } from 'vue-fastedgy';

const list = vi.fn().mockResolvedValue({ items: [{ id: 7 }, { id: 9 }], total: 2 });
let held;

mount({
    setup() {
        held = useApiCollection('company', { fields: 'id,name' }, { api: { list }, refreshDelay: 0 });

        return () => null;
    },
});

await flushPromises();

notifyChanged({ model: 'company', id: 7, action: 'deleted' });
await flushPromises();

expect(held.items.value).toEqual([{ id: 9 }]);
expect(list).toHaveBeenCalledTimes(1);
```

Unmount between tests: the bus outlives one, and a listener left attached is heard by the
next.

## Related

[Realtime overview](overview.md){ .md-button }
[Server side](../../features/realtime/guide.md){ .md-button }
[Bus](../bus/overview.md){ .md-button }
