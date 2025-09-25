# Metadata Store User Guide

This guide shows you how to use the Metadata Store in your Vue.js components with practical patterns.

## Using in Components

```vue
<script setup>
import { useMetadataStore } from 'vue-fastedgy'
import { onMounted, computed } from 'vue'

const metadataStore = useMetadataStore()

const userFields = computed(() => {
  const metadata = metadataStore.getMetadata('User')
  return metadata?.fields || {}
})

onMounted(async () => {
  // Load metadata on component mount
  await metadataStore.getMetadatas()
})
</script>
```

## Form Field Discovery

Use metadata to understand what fields are available for a model:

```vue
<template>
  <div>
    <h3>User Fields:</h3>
    <ul>
      <li v-for="(field, name) in userFields" :key="name">
        <strong>{{ name }}</strong>: {{ field.type }}
        <span v-if="field.required">(required)</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { useMetadataStore } from 'vue-fastedgy'
import { computed, onMounted } from 'vue'

const metadataStore = useMetadataStore()

const userFields = computed(() => {
  const metadata = metadataStore.getMetadata('User')
  return metadata?.fields || {}
})

onMounted(async () => {
  await metadataStore.getMetadatas()
})
</script>
```

## Validation Helper

Build validation rules from metadata:

```javascript
import { useMetadataStore } from 'vue-fastedgy'

const metadataStore = useMetadataStore()

const validateField = async (modelName, fieldName, value) => {
  const metadata = await metadataStore.getMetadata(modelName)
  const field = metadata?.fields?.[fieldName]

  if (!field) return null

  // Required validation
  if (field.required && (!value || value === '')) {
    return `${fieldName} is required`
  }

  // String length validation
  if (field.type === 'string' && field.max_length && value.length > field.max_length) {
    return `${fieldName} must be ${field.max_length} characters or less`
  }

  // Number range validation
  if (field.type === 'integer' || field.type === 'number') {
    const num = Number(value)
    if (field.minimum !== undefined && num < field.minimum) {
      return `${fieldName} must be at least ${field.minimum}`
    }
    if (field.maximum !== undefined && num > field.maximum) {
      return `${fieldName} must be at most ${field.maximum}`
    }
  }

  return null
}

// Usage in component
const errors = reactive({})

const validateUserForm = async (formData) => {
  errors.email = await validateField('User', 'email', formData.email)
  errors.age = await validateField('User', 'age', formData.age)

  // Remove null errors
  Object.keys(errors).forEach(key => {
    if (errors[key] === null) {
      delete errors[key]
    }
  })

  return Object.keys(errors).length === 0
}
```

## Loading States

Handle loading and error states properly:

```vue
<template>
  <div>
    <div v-if="metadataStore.loading">
      Loading metadata...
    </div>

    <div v-else-if="metadataStore.error">
      Error loading metadata: {{ metadataStore.error.message }}
      <button @click="retry">Retry</button>
    </div>

    <div v-else-if="metadata">
      <h3>{{ modelName }} Fields</h3>
      <div v-for="(field, name) in metadata.fields" :key="name">
        {{ name }}: {{ field.type }}
      </div>
    </div>

    <div v-else>
      No metadata available
    </div>
  </div>
</template>

<script setup>
import { useMetadataStore } from 'vue-fastedgy'
import { computed, onMounted } from 'vue'

const props = defineProps(['modelName'])
const metadataStore = useMetadataStore()

const metadata = computed(() =>
  metadataStore.getMetadata(props.modelName)
)

const retry = async () => {
  await metadataStore.fetchMetadatas()
}

onMounted(async () => {
  await metadataStore.getMetadatas()
})
</script>
```

## Model Discovery

List all available models:

```vue
<template>
  <div>
    <h3>Available Models</h3>
    <ul>
      <li v-for="modelName in availableModels" :key="modelName">
        <router-link :to="`/models/${modelName}`">
          {{ modelName }}
        </router-link>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { useMetadataStore } from 'vue-fastedgy'
import { computed, onMounted } from 'vue'

const metadataStore = useMetadataStore()

const availableModels = computed(() => {
  const metadata = metadataStore.getMetadatas()
  return metadata ? Object.keys(metadata) : []
})

onMounted(async () => {
  await metadataStore.getMetadatas()
})
</script>
```

## Conditional Field Display

Show/hide fields based on metadata:

```vue
<template>
  <form>
    <div
      v-for="(field, name) in visibleFields"
      :key="name"
      class="form-field"
    >
      <label>
        {{ field.label || name }}
        <span v-if="field.required">*</span>
      </label>

      <input
        v-if="field.type === 'string'"
        :type="getInputType(field)"
        :maxlength="field.max_length"
        :required="field.required"
      />

      <input
        v-else-if="field.type === 'integer'"
        type="number"
        :min="field.minimum"
        :max="field.maximum"
        :required="field.required"
      />

      <select
        v-else-if="field.choices"
        :required="field.required"
      >
        <option value="">Choose...</option>
        <option
          v-for="choice in field.choices"
          :key="choice.value"
          :value="choice.value"
        >
          {{ choice.display_name }}
        </option>
      </select>
    </div>
  </form>
</template>

<script setup>
import { useMetadataStore } from 'vue-fastedgy'
import { computed, onMounted } from 'vue'

const props = defineProps(['modelName', 'hideFields'])

const metadataStore = useMetadataStore()

const visibleFields = computed(() => {
  const metadata = metadataStore.getMetadata(props.modelName)
  if (!metadata?.fields) return {}

  const fields = { ...metadata.fields }

  // Hide specified fields
  if (props.hideFields) {
    props.hideFields.forEach(fieldName => {
      delete fields[fieldName]
    })
  }

  return fields
})

const getInputType = (field) => {
  if (field.format === 'email') return 'email'
  if (field.format === 'password') return 'password'
  if (field.format === 'url') return 'url'
  return 'text'
}

onMounted(async () => {
  await metadataStore.getMetadatas()
})
</script>
```
