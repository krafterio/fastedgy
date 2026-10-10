# Metadata Store User Guide

## Reading the metadata

`getMetadatas()` resolves to every model, keyed by its metadata name, and `getMetadata(name)` to
one of them. Both are asynchronous, and resolve to `null` when nothing is held: no account signed
in, or a read that failed. A screen reads once mounted and keeps what the promise resolves to:

```vue
<script setup>
import { onMounted, ref } from 'vue';
import { useMetadataStore } from 'vue-fastedgy';

const props = defineProps({ model: { type: String, required: true } });

const metadataStore = useMetadataStore();
const metadata = ref(null);

onMounted(async () => {
    metadata.value = await metadataStore.getMetadata(props.model);
});
</script>

<template>
  <ul v-if="metadata">
    <li v-for="field in metadata.fields" :key="field.name">
      {{ field.label }} <small>{{ field.type }}</small>
    </li>
  </ul>
</template>
```

A `computed` calling `getMetadata` holds a promise, not the metadata: `?.fields` reads nothing from
it, and the screen stays empty.

## What a model says

| Key | |
|---|---|
| `name` | Its metadata name, its class in snake_case (`ProductCategory` gives `product_category`) |
| `api_name` | The name its routes answer under, its table name |
| `label`, `label_plural` | Its name for a person |
| `fields` | Its fields, by name |
| `searchable`, `search_field`, `searchable_fields` | Whether a fulltext search reads it, the field the search is matched on, the fields it covers |
| `sortable`, `sortable_field` | Whether its records keep a manual order, and the field holding it (`sequence`) |
| `has_extra_fields` | Whether a workspace can add fields to it |
| `synchronizable`, `synchronizable_mode` | Whether an offline client replicates it, and how much (`full`, `partial`) |

## What a field says

| Key | |
|---|---|
| `name`, `label` | Its name, and its name for a person |
| `type` | `char`, `text`, `integer`, `float`, `decimal`, `boolean`, `date`, `datetime`, `json`, `choice`, `char_choice`, `many2one`, `one2one`, `one2many`, `many2many`; for the other fields, the name of their class in snake_case without `Field` (`email`, `time`) |
| `required` | Whether a new record must give it: it is not nullable, not read only, and has no default |
| `readonly` | Whether no write can set it |
| `default` | The value a new record starts with, `null` when there is none or when the server computes it on save |
| `choices` | For a choice field, its values and their labels, `{ value: label }`; `null` otherwise |
| `searchable`, `filter_operators` | Whether a filter can read it, and with which operators |
| `target`, `targets`, `inverse` | For a relation, the model it leads to (`targets` for a reference to several), and the field of that model leading back |
| `extra` | Whether a workspace added it, under a name starting with `extra_` |
| `local_placeholder` | What an offline client shows until the server fills it in (`DRAFT-{seq}`) |

## Choices

`choices` is an object, from the value the API reads and writes to its label:

```javascript
const metadata = await useMetadataStore().getMetadata('product');

metadata.fields.status.choices; // { draft: 'Draft', published: 'Published' }
metadata.fields.status.default; // 'draft'
```

A select walks it as an object, the label first:

```vue
<select v-model="product.status">
  <option v-for="(label, value) in field.choices" :key="value" :value="value">{{ label }}</option>
</select>
```

`Object.entries(field.choices)` gives the same pairs as an array, `[value, label]`.

## Loading and errors

`loading` is `true` while a read runs, and `error` holds what the last one ran into. A read that
fails holds nothing, so the next call reads again:

```vue
<script setup>
import { onMounted, ref } from 'vue';
import { useMetadataStore } from 'vue-fastedgy';

const props = defineProps({ model: { type: String, required: true } });

const metadataStore = useMetadataStore();
const metadata = ref(null);

const load = async () => {
    metadata.value = await metadataStore.getMetadata(props.model);
};

onMounted(load);
</script>

<template>
  <p v-if="metadataStore.loading">Loading the fields...</p>
  <p v-else-if="metadataStore.error">
    The fields could not be read.
    <button type="button" @click="load">Retry</button>
  </p>
  <ul v-else-if="metadata">
    <li v-for="field in metadata.fields" :key="field.name">{{ field.label }}</li>
  </ul>
</template>
```

`fetchMetadatas()` reads again even what is held, and resolves to what the read ran into, `null`
when it went well.

## Reading again

What a model describes can change while the application runs: a workspace adds a field to it.
Whatever knows announces it on the bus, the store forgets what it holds, and the next call reads:

```javascript
import { bus, METADATA_INVALIDATED } from 'vue-fastedgy';

bus.trigger(METADATA_INVALIDATED);
```

A read asked before the announcement does not land. A sign-out forgets everything too: the next
account may see other fields.

## The prefix

The store reads `/dataset/metadatas` under its prefix, none by default:

```javascript
useMetadataStore().setPrefix('/console'); // reads /console/dataset/metadatas
```

An application serving one workspace at a time sets `/{workspace}`. With the workspaces installed
(`createWorkspaces()`), the store reads under the slug of the current workspace and keeps one set
per workspace, and coming back to one reads nothing. `setMetadataScope(resolver)` does the same for
another kind of scope: from the prefix, the resolver answers the scope to keep the set under and
the prefix to read it at, `{ scope, prefix }`.

## Testing

`setMetadatas(map)` holds a set without reading it, which is what a test does before mounting a
screen that reads the metadata:

```javascript
import { createPinia, setActivePinia } from 'pinia';
import { useMetadataStore } from 'vue-fastedgy';

setActivePinia(createPinia());

useMetadataStore().setMetadatas({
    product: { name: 'product', api_name: 'products', fields: {} },
});
```
