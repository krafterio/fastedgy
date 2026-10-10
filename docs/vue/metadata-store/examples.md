# Metadata Store Examples

What a screen can draw from the metadata alone, without a line written per model. Every example
awaits the store: `getMetadata` and `getMetadatas` return promises.

## Form fields from the metadata

The fields a form edits, with what an input needs to know about each:

```javascript
import { useMetadataStore } from 'vue-fastedgy';

async function formFields(model) {
    const metadata = await useMetadataStore().getMetadata(model);

    return Object.values(metadata?.fields ?? {})
        .filter((field) => !field.readonly && !field.target)
        .map((field) => ({
            name: field.name,
            label: field.label,
            type: field.type,
            required: field.required,
            choices: field.choices ? Object.entries(field.choices) : null,
            default: field.default,
        }));
}
```

The relations are left out here: an input for one picks a record of its `target`.

## Required fields

The metadata says which fields a new record must give, not their lengths or their ranges: the
server checks those when the record is written.

```javascript
function missingFields(metadata, values) {
    return Object.values(metadata.fields)
        .filter((field) => field.required && (values[field.name] ?? '') === '')
        .map((field) => field.label);
}
```

## Table columns

The label and the type of a column, a path through the relations included:

```javascript
import { resolveFieldPath, useMetadataStore } from 'vue-fastedgy';

async function tableColumns(model, keys) {
    const metadatas = await useMetadataStore().getMetadatas();

    return keys.map((key) => {
        const field = resolveFieldPath(metadatas, model, key)?.field;

        return { key, label: field?.label ?? key, type: field?.type ?? null };
    });
}

await tableColumns('product', ['name', 'price', 'category.name']);
```

`useDataTable` takes the type of its columns from the metadata the same way.

## Model catalogue

Every model the server describes, with its label and what it offers:

```javascript
import { useMetadataStore } from 'vue-fastedgy';

async function modelCatalogue() {
    const metadatas = await useMetadataStore().getMetadatas();

    return Object.values(metadatas ?? {}).map((metadata) => ({
        name: metadata.name,
        label: metadata.label_plural,
        searchable: metadata.searchable,
        sortable: metadata.sortable,
        fields: Object.keys(metadata.fields).length,
    }));
}
```

## A dynamic form component

A form for any model, saving a new record through [`useApiModel`](../api-service/overview.md):

```vue
<template>
  <form v-if="fields.length" @submit.prevent="save">
    <div v-for="field in fields" :key="field.name">
      <label :for="field.name">
        {{ field.label }}
        <span v-if="field.required">*</span>
      </label>

      <select v-if="field.choices" :id="field.name" v-model="values[field.name]" :required="field.required">
        <option v-for="(label, value) in field.choices" :key="value" :value="value">{{ label }}</option>
      </select>

      <input v-else-if="field.type === 'boolean'" :id="field.name" v-model="values[field.name]" type="checkbox" />

      <input
        v-else-if="NUMBER_TYPES.includes(field.type)"
        :id="field.name"
        v-model.number="values[field.name]"
        type="number"
        :required="field.required"
      />

      <input
        v-else-if="field.type === 'date'"
        :id="field.name"
        v-model="values[field.name]"
        type="date"
        :required="field.required"
      />

      <textarea
        v-else-if="field.type === 'text'"
        :id="field.name"
        v-model="values[field.name]"
        :required="field.required"
      />

      <input v-else :id="field.name" v-model="values[field.name]" type="text" :required="field.required" />
    </div>

    <p v-if="failed" role="alert">The record could not be saved.</p>

    <button type="submit" :disabled="saving">{{ saving ? 'Saving...' : 'Save' }}</button>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import { useApiModel, useMetadataStore } from 'vue-fastedgy';

const NUMBER_TYPES = ['integer', 'small_integer', 'big_integer', 'float', 'decimal'];

const props = defineProps({ model: { type: String, required: true } });
const emit = defineEmits(['saved']);

const metadataStore = useMetadataStore();
const api = useApiModel(props.model);

const fields = ref([]);
const values = reactive({});
const saving = ref(false);
const failed = ref(false);

onMounted(async () => {
    const metadata = await metadataStore.getMetadata(props.model);

    fields.value = Object.values(metadata?.fields ?? {}).filter((field) => !field.readonly && !field.target);

    for (const field of fields.value) {
        values[field.name] = field.default ?? (field.type === 'boolean' ? false : null);
    }
});

const save = async () => {
    saving.value = true;
    failed.value = false;

    try {
        const response = await api.create({ ...values });

        emit('saved', response.data);
    } catch {
        failed.value = true;
    } finally {
        saving.value = false;
    }
};
</script>
```

## Model field inspector

A component listing what the metadata says of each field of a model:

```vue
<template>
  <section>
    <h3>{{ metadata?.label ?? model }}</h3>

    <p v-if="metadataStore.loading">Loading the fields...</p>

    <dl v-else-if="metadata">
      <template v-for="field in metadata.fields" :key="field.name">
        <dt>{{ field.label }} <code>{{ field.name }}</code></dt>
        <dd>
          {{ field.type }}
          <span v-if="field.target">to {{ field.target }}</span>
          <span v-if="field.required">, required</span>
          <span v-if="field.readonly">, read only</span>
          <span v-if="field.choices">: {{ Object.values(field.choices).join(', ') }}</span>
        </dd>
      </template>
    </dl>
  </section>
</template>

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
```
