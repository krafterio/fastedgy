# API Model

**The routes FastEdgy generates for a model, reached by its metadata name**

`useApiModel` calls the routes the [API Routes Generator](../../features/api-routes/overview.md)
creates for a model: list, read, create, update, delete, export and import, and the actions added
beside them. It builds the URL, the query parameters and the `X-Fields` and `X-Filter` headers, and
returns the response of the [fetcher](../fetcher/overview.md), the payload under `data`.

## Key features

- **Every generated route**: `list`, `get`, `create`, `update`, `delete`, `export`,
  `importTemplate`, `import`, and `siblings` for a model that enables it.
- **Named by its metadata**: the model is called by its metadata name (`product`), and the URL is
  built from the `api_name` the [metadata store](../metadata-store/overview.md) holds for it.
- **FastEdgy conventions**: `fields` sent as `X-Fields`, `filter` as `X-Filter`, `page` and `size`
  as `limit` and `offset`, `orderBy` as `order_by`.
- **A prefix**: the routes of a model served under another path, `/console` for instance.
- **Its own writes announced**: a create, an update or a delete reaches every holder watching the
  model, in this tab, straight away.
- **Actions beside the generated routes**: `action(method, path)`, the URL resolved like the others.

## Quick example

```javascript
import { useApiModel } from 'vue-fastedgy';

const api = useApiModel('product');

const response = await api.list({ page: 1, size: 25, fields: ['id', 'name', 'price'], orderBy: 'price:desc' });

response.data.items; // the products of the first page
response.data.total; // how many products there are, every page together

await api.update(42, { price: 19.9 });
```

## Get started

[User Guide](guide.md){ .md-button .md-button--primary }
