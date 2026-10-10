# API Model - User guide

## One function per model

The model is named by its metadata name, its class in snake_case (`product`).
`useApiModel` builds the URL from the `api_name` the metadata gives for it (`/products`), and the
changes it announces carry the name it was given. A name the metadata does not hold goes into the
URL as it is.

An application keeps one function per model, the place for what belongs to it:

```javascript
// composables/api/product.js
import { useApiModel } from 'vue-fastedgy';

export function useProductApiModel(params = {}) {
    return useApiModel('product', params);
}
```

`useDataIterator`, `useApiForm` and `useApiOptions` take an api model where they take a model
name, and `useRecordContext` takes the one of its record.

## Options

`useApiModel(name, options)` takes:

| Option | |
|---|---|
| `prefix` | What the URL starts with, before the `api_name`. See [Prefix](#prefix). |
| `headers` | Headers sent with every request. |

Every method takes the same options as its last argument, laid over these for that call, option
by option.

## Reading

```vue
<script setup>
import { onMounted, ref } from 'vue';
import { useProductApiModel } from '@/composables/api/product';

const api = useProductApiModel();
const products = ref([]);
const total = ref(0);

onMounted(async () => {
    const response = await api.list({
        page: 1,
        size: 25,
        fields: ['id', 'name', 'price', 'category.name'],
        filter: ['is_active', '=', true],
        orderBy: ['category.name', 'price:desc'],
    });

    products.value = response.data.items;
    total.value = response.data.total;
});
</script>
```

| Query | Sent as |
|---|---|
| `page`, `size` | `limit` = `size`, `offset` = `(page - 1) * size`; `size` alone sets the `limit` |
| `limit`, `offset` | as they are, over what `page` and `size` say |
| `fields` | `X-Fields`, from an array or a comma-separated string |
| `filter` | `X-Filter`, a [Query Builder](../../features/query-builder/overview.md) expression; nothing when it is empty |
| `orderBy` | `order_by`, `field:direction` terms, from an array or a comma-separated string |

A list answers the [pagination](../../features/pagination/overview.md) of the server under `data`:
`items`, `total`, `limit`, `offset` and `total_pages`. Without `size` or `limit`, the server reads
its default `limit`, 50 rows.

A record is read by its id, and `data` holds it:

```javascript
const response = await api.get(42, { fields: ['id', 'name', 'description'] });

response.data.name;
```

A list on screen, with its pages, its order and its URL, is held by the
[data iterator](../query-builder/guide.md#the-list); one that follows the writes of everyone, by
[`useApiCollection`](../realtime/guide.md#holding-a-list).

## Writing

```javascript
const created = await api.create({ name: 'Desk lamp', price: 39.9 }, { fields: ['id', 'name'] });

await api.update(created.data.id, { price: 34.9 });
await api.delete(created.data.id);
```

`create` and `update` answer the record under `data`, with the fields `fields` asks for. The
payload is sent with `undefined` and `''` turned into `null`, at any depth.

Each write announces itself in this tab as a change of the model, the fields of its payload as
`changed`: every holder and every `useResourceChanged` watching the model reacts
([Realtime](../realtime/guide.md#your-own-writes)).

A request the server refuses throws an `HttpError`, its status under `error.response.status` and
the body of the answer under `error.data` ([Fetcher](../fetcher/advanced.md#httperror-handling)).

## Export and import

```javascript
const exported = await api.export({
    format: 'xlsx',
    fields: ['name', 'price', 'category.name'],
    filter: ['is_active', '=', true],
});
const blob = await exported.blob();

const result = await api.import(file, { delimiter: ';' }); // a File the user picked

result.data.created;
```

`export` and `importTemplate` answer the file itself, `csv` by default, `xlsx` or `ods`. In an
export, `relationDelimiter` (`newline`, `semicolon` or `comma`) separates the values of a relation
in one cell; `createApiModel` sets it for the whole application:

```javascript
import { createApiModel } from 'vue-fastedgy';

app.use(createApiModel({ export: { defaultRelationDelimiter: 'semicolon' } }));
```

`import` sends a CSV, XLSX or ODS `File`, with the `delimiter` of a CSV when the server should not
detect it, and answers `success`, `errors`, `created` and `updated` under `data`. A file whose rows
the server refuses throws, the same counts and `error_details` (the row, the error, its data) under
`error.data.detail`.

## Actions beside the generated routes

```javascript
await api.action('post', '/42/activate');

const neighbours = await api.siblings(42, { filter: ['is_active', '=', true], orderBy: 'name:asc' });

neighbours.data; // { previous: 17, next: 58 }
```

`action(method, path, body, query, options)` reaches a route the model answers to outside the
generated ones, a [custom action](../../features/api-routes/advanced.md#custom-actions) for
instance; `path` is what follows the model in the URL. A `get` or a `delete` sends the query as
parameters, a `post`, a `patch` or a `put` sends the body, and the `fields` and the `filter` of the
query go as headers either way. Unlike `create`, `update` and `delete`, an action announces nothing
in the tab.

`siblings` reads the [siblings route](../../features/api-routes/guide.md#record-siblings) of a
model that enables it: the ids either side of one, in the list a filter and an order describe.

## Prefix

```javascript
const api = useApiModel('product', { prefix: '/console' });

await api.list({ size: 25 }); // GET /console/products?limit=25
```

The prefix comes after the base URL of the fetcher and before the `api_name`. `api.prefix` gives it
back, for what reaches the server beside the routes of the model: its custom views, its relations.

## Extending a model

The function of a model is where its own endpoints go:

```javascript
import { useApiModel } from 'vue-fastedgy';

export function useProductApiModel(params = {}) {
    const api = useApiModel('product', params);

    return {
        ...api,
        activate: (id) => api.action('post', `/${id}/activate`),
    };
}
```
