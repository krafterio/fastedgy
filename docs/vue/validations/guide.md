# Validations User Guide

This guide shows you how to use the `formatValidationErrors` function in real Vue.js applications.

## Vue Component Usage

Use the function to display API validation errors in your components:

```vue
<template>
  <div>
    <form @submit.prevent="handleSubmit">
      <div>
        <label>Email:</label>
        <input v-model="formData.email" type="email" required />
      </div>

      <div>
        <label>Password:</label>
        <input v-model="formData.password" type="password" required />
      </div>

      <!-- Show formatted validation errors -->
      <div v-if="validationError" class="error-message">
        {{ validationError }}
      </div>

      <button type="submit" :disabled="loading">
        {{ loading ? 'Submitting...' : 'Submit' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { formatValidationErrors, useFetcher } from 'vue-fastedgy'
import { ref, reactive } from 'vue'

const fetcher = useFetcher()

const formData = reactive({
  email: '',
  password: ''
})

const loading = ref(false)
const validationError = ref('')

const handleSubmit = async () => {
  loading.value = true
  validationError.value = ''

  try {
    const response = await fetcher.post('/auth/login', formData)
    console.log('Success:', response.data)
  } catch (error) {
    // Format and display validation errors
    const errorMessage = formatValidationErrors(error, 'Login failed')
    validationError.value = errorMessage
    console.error('Validation errors:', errorMessage)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.error-message {
  color: red;
  margin: 1rem 0;
  white-space: pre-line; /* Preserve line breaks for multiple errors */
}
</style>
```

## Advanced Error Handling

Handle different types of API errors:

```javascript
import { formatValidationErrors, HttpError } from 'vue-fastedgy'

const handleApiError = (error) => {
  if (error instanceof HttpError) {
    const status = error.response.status

    switch (status) {
      case 400:
        // Bad Request - usually validation errors
        return formatValidationErrors(error, 'Invalid form data')

      case 401:
        return 'Invalid credentials'

      case 403:
        return 'Access denied'

      case 422:
        // Unprocessable Entity - Pydantic validation errors
        return formatValidationErrors(error, 'Please check your input')

      case 500:
        return 'Server error. Please try again later.'

      default:
        return formatValidationErrors(error, 'Something went wrong')
    }
  }

  // Network or other errors
  return 'Connection error. Please check your internet connection.'
}

// Usage in component
const submitForm = async () => {
  try {
    await fetcher.post('/api/users', userData)
  } catch (error) {
    const errorMessage = handleApiError(error)
    showNotification('error', errorMessage)
  }
}
```

## Form Validation Component

Create a reusable form component with validation error display:

```vue
<template>
  <div class="validated-form">
    <slot :errors="fieldErrors" :hasErrors="hasValidationErrors" />

    <!-- Global error display -->
    <div v-if="globalError" class="global-error">
      {{ globalError }}
    </div>
  </div>
</template>

<script setup>
import { formatValidationErrors } from 'vue-fastedgy'
import { ref, computed } from 'vue'

const emit = defineEmits(['submit', 'error'])

const globalError = ref('')
const fieldErrors = ref({})

const hasValidationErrors = computed(() => {
  return Object.keys(fieldErrors.value).length > 0 || !!globalError.value
})

const handleSubmit = async (submitFunction) => {
  clearErrors()

  try {
    const result = await submitFunction()
    emit('submit', result)
  } catch (error) {
    handleError(error)
    emit('error', error)
  }
}

const clearErrors = () => {
  globalError.value = ''
  fieldErrors.value = {}
}

const handleError = (error) => {
  const errorData = error?.data?.detail

  if (!errorData) {
    globalError.value = 'An unexpected error occurred'
    return
  }

  if (typeof errorData === 'string') {
    globalError.value = errorData
    return
  }

  if (Array.isArray(errorData)) {
    // Parse field-specific errors
    errorData.forEach(err => {
      if (err.loc && err.loc.length > 1) {
        const fieldName = err.loc[err.loc.length - 1]
        fieldErrors.value[fieldName] = err.msg
      } else {
        // Global error
        globalError.value = formatValidationErrors(error, 'Validation failed')
      }
    })

    // If no field-specific errors, show as global
    if (Object.keys(fieldErrors.value).length === 0) {
      globalError.value = formatValidationErrors(error, 'Validation failed')
    }
  }
}

defineExpose({
  handleSubmit,
  clearErrors,
  hasValidationErrors
})
</script>

<style scoped>
.global-error {
  color: red;
  margin: 1rem 0;
  padding: 1rem;
  border: 1px solid #ffcdd2;
  background-color: #ffebee;
  border-radius: 4px;
}
</style>
```

Usage of the validated form component:

```vue
<template>
  <ValidatedForm ref="form" @submit="onSuccess" @error="onError">
    <template #default="{ errors }">
      <div>
        <label>Name:</label>
        <input v-model="userData.name" type="text" required />
        <span v-if="errors.name" class="field-error">{{ errors.name }}</span>
      </div>

      <div>
        <label>Email:</label>
        <input v-model="userData.email" type="email" required />
        <span v-if="errors.email" class="field-error">{{ errors.email }}</span>
      </div>

      <button type="button" @click="submitForm">
        Create User
      </button>
    </template>
  </ValidatedForm>
</template>

<script setup>
import { useFetcher } from 'vue-fastedgy'
import { reactive, ref } from 'vue'
import ValidatedForm from './ValidatedForm.vue'

const fetcher = useFetcher()
const form = ref()

const userData = reactive({
  name: '',
  email: ''
})

const submitForm = () => {
  form.value.handleSubmit(() => {
    return fetcher.post('/users', userData)
  })
}

const onSuccess = (result) => {
  console.log('User created:', result)
  // Reset form
  userData.name = ''
  userData.email = ''
}

const onError = (error) => {
  console.error('Form submission failed:', error)
}
</script>

<style scoped>
.field-error {
  color: red;
  font-size: 0.875rem;
  display: block;
  margin-top: 0.25rem;
}
</style>
```

## Error Format Examples

### Pydantic Array Errors

```javascript
const arrayError = {
  data: {
    detail: [
      {
        loc: ['body', 'email'],
        msg: 'field required',
        type: 'value_error.missing'
      },
      {
        loc: ['body', 'age'],
        msg: 'ensure this value is greater than or equal to 0',
        type: 'value_error.number.not_ge',
        ctx: { limit_value: 0 }
      }
    ]
  }
}

const formatted = formatValidationErrors(arrayError)
console.log(formatted)
// Output:
// "• body → email: field required
// • body → age: ensure this value is greater than or equal to 0"
```

### Simple String Errors

```javascript
const stringError = {
  data: {
    detail: "Username already exists"
  }
}

const formatted = formatValidationErrors(stringError)
console.log(formatted)
// Output: "Username already exists"
```

### Nested Field Errors

```javascript
const nestedError = {
  data: {
    detail: [{
      loc: ['body', 'address', 'zipcode'],
      msg: 'invalid zip code format'
    }]
  }
}

const formatted = formatValidationErrors(nestedError)
console.log(formatted)
// Output: "body → address → zipcode: invalid zip code format"
```

### With Default Message

```javascript
const unknownError = {
  data: {} // No detail property
}

const formatted = formatValidationErrors(unknownError, 'Something went wrong')
console.log(formatted)
// Output: "Something went wrong"

// Without default message
const formatted2 = formatValidationErrors(unknownError)
console.log(formatted2)
// Output: "Erreur inconnue"
```

## Integration with Toast Notifications

```javascript
import { formatValidationErrors } from 'vue-fastedgy'

const showValidationToast = (error) => {
  const message = formatValidationErrors(error, 'Please check your input')

  // With a toast library like vue-toastification
  toast.error(message, {
    timeout: 5000,
    closeOnClick: true,
    pauseOnFocusLoss: false,
    pauseOnHover: true
  })
}

// Usage in form submission
const handleFormSubmit = async () => {
  try {
    await submitData()
    toast.success('Form submitted successfully!')
  } catch (error) {
    showValidationToast(error)
  }
}
```
