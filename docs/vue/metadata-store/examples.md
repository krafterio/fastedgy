# Metadata Store Examples

This guide shows concrete examples of what you can build using the Metadata Store to create dynamic, metadata-driven UIs.

## Dynamic Form Generation

Build form fields automatically from metadata:

```javascript
import { useMetadataStore } from 'vue-fastedgy/services/metadata'

// Build form fields from metadata
const metadataStore = useMetadataStore()
const userMetadata = await metadataStore.getMetadata('User')

const formFields = Object.entries(userMetadata.fields).map(([name, field]) => ({
  name,
  type: field.type,
  required: field.required,
  label: field.label || name,
  placeholder: field.help_text
}))
```

## Client-Side Validation

Create validation rules from backend constraints:

```javascript
const validateField = (fieldName, value) => {
  const fieldMeta = userMetadata.fields[fieldName]

  if (fieldMeta.required && !value) {
    return `${fieldName} is required`
  }

  if (fieldMeta.max_length && value.length > fieldMeta.max_length) {
    return `${fieldName} must be ${fieldMeta.max_length} characters or less`
  }

  return null
}
```

## Dynamic UI Components

Generate different input types based on metadata:

```vue
<template>
  <div v-for="(field, name) in userFields" :key="name">
    <label>{{ field.label || name }}</label>

    <!-- Different input types based on metadata -->
    <input
      v-if="field.type === 'string'"
      :type="field.format === 'email' ? 'email' : 'text'"
      :required="field.required"
      :maxlength="field.max_length"
    />

    <input
      v-else-if="field.type === 'integer'"
      type="number"
      :min="field.minimum"
      :max="field.maximum"
      :required="field.required"
    />

    <select v-else-if="field.choices" :required="field.required">
      <option v-for="choice in field.choices" :key="choice.value" :value="choice.value">
        {{ choice.display_name }}
      </option>
    </select>
  </div>
</template>
```

## Admin Table Columns

Build table columns from metadata:

```javascript
const buildTableColumns = (modelName) => {
  const metadataStore = useMetadataStore()
  const metadata = metadataStore.getMetadata(modelName)

  return Object.entries(metadata.fields).map(([name, field]) => ({
    key: name,
    title: field.label || name,
    sortable: field.type !== 'text',
    filterable: field.choices ? 'select' : field.type === 'string' ? 'search' : 'range'
  }))
}
```

## API Documentation Generator

Generate interactive API docs from metadata:

```javascript
const generateApiDocs = () => {
  const metadataStore = useMetadataStore()
  const allMetadata = metadataStore.getMetadatas()

  return Object.entries(allMetadata).map(([model, metadata]) => ({
    model,
    fields: metadata.fields,
    endpoints: [
      { method: 'GET', url: `/${model.toLowerCase()}s/` },
      { method: 'POST', url: `/${model.toLowerCase()}s/`, body: metadata.fields },
      { method: 'GET', url: `/${model.toLowerCase()}s/{id}/` },
      { method: 'PUT', url: `/${model.toLowerCase()}s/{id}/`, body: metadata.fields }
    ]
  }))
}
```

## Simple Dynamic Form Component

Here's a practical example of a dynamic form component:

```vue
<template>
  <div class="dynamic-form">
    <h2>{{ modelName }} Form</h2>

    <form @submit.prevent="handleSubmit">
      <div
        v-for="(field, fieldName) in fields"
        :key="fieldName"
        class="form-group"
      >
        <label :for="fieldName">
          {{ field.label || fieldName }}
          <span v-if="field.required" class="required">*</span>
        </label>

        <!-- String fields -->
        <input
          v-if="field.type === 'string'"
          :id="fieldName"
          v-model="formData[fieldName]"
          :type="getInputType(field)"
          :required="field.required"
          :maxlength="field.max_length"
          :placeholder="field.help_text"
        />

        <!-- Number fields -->
        <input
          v-else-if="field.type === 'integer' || field.type === 'number'"
          :id="fieldName"
          v-model="formData[fieldName]"
          type="number"
          :required="field.required"
          :min="field.minimum"
          :max="field.maximum"
        />

        <!-- Boolean fields -->
        <input
          v-else-if="field.type === 'boolean'"
          :id="fieldName"
          v-model="formData[fieldName]"
          type="checkbox"
        />

        <!-- Choice fields -->
        <select
          v-else-if="field.choices"
          :id="fieldName"
          v-model="formData[fieldName]"
          :required="field.required"
        >
          <option value="">Choose {{ field.label || fieldName }}...</option>
          <option
            v-for="choice in field.choices"
            :key="choice.value"
            :value="choice.value"
          >
            {{ choice.display_name }}
          </option>
        </select>
      </div>

      <button type="submit" :disabled="loading">
        {{ loading ? 'Saving...' : 'Save' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { useMetadataStore } from 'vue-fastedgy/services/metadata'
import { useFetcher } from 'vue-fastedgy/composables/fetcher'
import { ref, reactive, computed, onMounted } from 'vue'

const props = defineProps(['modelName'])
const emit = defineEmits(['saved'])

const metadataStore = useMetadataStore()
const fetcher = useFetcher()

const formData = reactive({})
const loading = ref(false)

const fields = computed(() => {
  const metadata = metadataStore.getMetadata(props.modelName)
  return metadata?.fields || {}
})

const getInputType = (field) => {
  switch (field.format) {
    case 'email': return 'email'
    case 'password': return 'password'
    case 'url': return 'url'
    case 'date': return 'date'
    default: return 'text'
  }
}

const handleSubmit = async () => {
  loading.value = true

  try {
    const response = await fetcher.post(`/${props.modelName.toLowerCase()}s/`, formData)
    emit('saved', response.data)

    // Reset form
    Object.keys(formData).forEach(key => {
      formData[key] = ''
    })
  } catch (error) {
    console.error('Save error:', error)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await metadataStore.getMetadatas()

  // Initialize form data
  Object.entries(fields.value).forEach(([fieldName, field]) => {
    if (field.type === 'boolean') {
      formData[fieldName] = false
    } else {
      formData[fieldName] = ''
    }
  })
})
</script>

<style scoped>
.dynamic-form {
  max-width: 600px;
  margin: 0 auto;
}

.form-group {
  margin-bottom: 1rem;
}

label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.required {
  color: red;
}

input, select {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
}

button {
  background: #007bff;
  color: white;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
```

## Model Field Inspector

A simple component to inspect model fields:

```vue
<template>
  <div class="field-inspector">
    <h3>{{ modelName }} Fields</h3>

    <div v-if="loading">Loading metadata...</div>

    <div v-else-if="metadata" class="fields-list">
      <div
        v-for="(field, name) in metadata.fields"
        :key="name"
        class="field-item"
      >
        <strong>{{ name }}</strong>
        <span class="field-type">{{ field.type }}</span>
        <span v-if="field.required" class="required">required</span>
        <span v-if="field.max_length" class="constraint">max: {{ field.max_length }}</span>
        <div v-if="field.help_text" class="help-text">{{ field.help_text }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useMetadataStore } from 'vue-fastedgy/services/metadata'
import { computed, onMounted } from 'vue'

const props = defineProps(['modelName'])
const metadataStore = useMetadataStore()

const metadata = computed(() => metadataStore.getMetadata(props.modelName))
const loading = computed(() => metadataStore.loading)

onMounted(async () => {
  await metadataStore.getMetadatas()
})
</script>

<style scoped>
.field-item {
  padding: 0.5rem;
  border-bottom: 1px solid #eee;
}

.field-type {
  color: #666;
  font-style: italic;
  margin-left: 1rem;
}

.required {
  color: red;
  font-size: 0.8rem;
  margin-left: 0.5rem;
}

.constraint {
  color: #999;
  font-size: 0.8rem;
  margin-left: 0.5rem;
}

.help-text {
  font-size: 0.9rem;
  color: #666;
  margin-top: 0.25rem;
}
</style>
```
