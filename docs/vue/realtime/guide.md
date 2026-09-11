# Realtime - User Guide

## Holding the socket

One call, in the application shell, and nowhere else:

```vue
<script setup>
import { useRealtime } from 'vue-fastedgy';

useRealtime();
</script>
```

It opens the socket when an account is signed in, points it at the workspace being read, and
closes it on sign-out. The workspace comes from `useWorkspaceStore()`, which the router keeps
on the one in the URL.

A page with no workspace (an onboarding, an auth screen) has nothing to listen to: the socket
waits rather than opening on nothing.

An application that names its workspace another way passes its own source:

```javascript
import { useRoute } from 'vue-router';

useRealtime(() => useRoute().params.workspace ?? null);
```

A closed socket is reopened, later each time up to 30 seconds, so a tab left open through a
deploy or a laptop coming out of sleep finds its way back without hammering the server.

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
| `isDeleted` | `true` once the record was deleted anywhere. The screen can close itself. |
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
{ model: 'company', id: 42, action: 'updated', changed: ['name'], origin: null, truncated: false }
```

Events carry identifiers only: read the record back through the API rather than trusting
`changed` to tell you the new value.

### Reconnection

The handler is also called with `action: 'reconnected'` and no id when the socket comes back:

```javascript
useResourceChanged('company', ({ action }) => {
    // 'created' | 'updated' | 'deleted' | 'reconnected'
    reload();
});
```

Nothing is replayed. What happened while the socket was down was said to nobody, so the view
has to read again to stop showing a stale screen. That call is never held back by the
debounce. The holders do this for you.

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
the life of this page. The server hands it back on the announcement of that write, and the
socket drops a frame carrying our own: the local event already said it.

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
