# Metadata Store

**The metadata of the models, read once for the whole application**

The metadata store is a Pinia store holding what the `/dataset/metadatas` route of the
[Metadata Generator](../../features/metadata-generator/overview.md) describes: every model the
server exposes, by its metadata name, with its labels and its fields, their types, their filter
operators and their relations. The data iterator, the query builder and `useApiModel` read it, and
so does a screen drawing what the server describes.

## Key features

- **Asynchronous**: `getMetadatas()` and `getMetadata(name)` return a promise, which resolves to
  `null` when nothing is held: no account signed in, or a read that failed.
- **Read once**: the first call reads, the calls made meanwhile wait for that read, the next ones
  read nothing.
- **Signed in only**: nothing is read for a visitor, and a sign-out forgets what was read.
- **Read again on demand**: `METADATA_INVALIDATED` on the bus forgets it, and the next call reads.
- **One set per workspace**: under a `/{workspace}` prefix, with the workspaces installed, each
  workspace keeps its own, and coming back to one reads nothing.

## Quick example

```javascript
import { useMetadataStore } from 'vue-fastedgy';

const metadataStore = useMetadataStore();

const product = await metadataStore.getMetadata('product');

product?.api_name; // 'products'
product?.fields.status.choices; // { draft: 'Draft', published: 'Published' }
```

## Get started

[User Guide](guide.md){ .md-button .md-button--primary }
[Examples & Ideas](examples.md){ .md-button }
