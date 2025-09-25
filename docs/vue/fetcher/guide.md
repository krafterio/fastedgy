# Fetcher User Guide

This guide shows you how to use the Fetcher in real Vue.js applications with practical examples and patterns.

## REST Methods with Enhanced Options

The fetcher provides specific methods for each HTTP verb with enhanced capabilities:

```javascript
const fetcher = useFetcher()

// GET with query parameters and custom options
const response = await fetcher.get('/users', {
  params: { page: 1, limit: 20 }, // Auto query params
  id: 'users-list', // Custom ID for cancellation (use with fetcher.abort('users-list'))
  headers: { 'Custom-Header': 'value' }
})

// POST with automatic JSON handling
const userResponse = await fetcher.post('/users', {
  name: 'John Doe' // Auto JSON.stringify() + Content-Type
}, {
  id: 'create-user', // Can be aborted with fetcher.abort('create-user')
  headers: { 'X-Request-ID': 'abc123' }
})

// PUT/PATCH for updates
const updatedUser = await fetcher.put('/users/123', userData)
const patchedUser = await fetcher.patch('/users/123', { status: 'active' })

// DELETE with options
await fetcher.delete('/users/123', {
  id: 'delete-user', // Abortable with fetcher.abort('delete-user')
  headers: { 'X-Confirm': 'true' }
})
```

## Component Integration

Here's how to use the Fetcher in Vue components with automatic cleanup:

```vue
<template>
  <div>
    <ul v-if="users">
      <li v-for="user in users" :key="user.id">
        {{ user.name }}
        <button @click="updateUser(user.id)">Update</button>
        <button @click="deleteUser(user.id)">Delete</button>
      </li>
    </ul>
    <div v-if="loading">Loading...</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useFetcher } from 'vue-fastedgy'

const users = ref(null)
const loading = ref(true)
const fetcher = useFetcher()

onMounted(async () => {
  try {
    // GET with query parameters
    const response = await fetcher.get('/users', {
      params: { active: true, limit: 50 }
    })
    users.value = response.data
  } catch (error) {
    console.error('Failed to fetch users:', error)
  } finally {
    loading.value = false
  }
})

const updateUser = async (userId) => {
  // PATCH for partial updates
  const response = await fetcher.patch(`/users/${userId}`, {
    lastSeen: new Date().toISOString()
  })
  // Update local data
  const index = users.value.findIndex(u => u.id === userId)
  if (index >= 0) users.value[index] = response.data
}

const deleteUser = async (userId) => {
  // DELETE request
  await fetcher.delete(`/users/${userId}`)
  // Remove from local data
  users.value = users.value.filter(u => u.id !== userId)
}

// All requests automatically cancelled on component unmount
</script>
```

## Service Usage (No Auto-Abort)

For services that need to persist beyond component lifecycle:

```javascript
import { useFetcherService } from 'vue-fastedgy'

// In a service file
const fetcher = useFetcherService()

export const userService = {
  async getUsers(filters = {}) {
    const response = await fetcher.get('/users', { params: filters })
    return response.data
  },

  async createUser(userData) {
    const response = await fetcher.post('/users', userData)
    return response.data
  },

  async updateUser(id, userData) {
    const response = await fetcher.put(`/users/${id}`, userData)
    return response.data
  },

  async patchUser(id, updates) {
    const response = await fetcher.patch(`/users/${id}`, updates)
    return response.data
  },

  async deleteUser(id) {
    await fetcher.delete(`/users/${id}`)
    return true
  }
}
```

## Error Handling

```vue
<script setup>
import { ref } from 'vue'
import { useFetcher, HttpError } from 'vue-fastedgy'

const fetcher = useFetcher()
const error = ref(null)

const handleApiCall = async () => {
  try {
    error.value = null
    const response = await fetcher.post('/api/action', { data: 'value' })
    // Handle success
  } catch (err) {
    if (err instanceof HttpError) {
      error.value = `API Error ${err.response.status}: ${err.message}`
      console.log('Error data:', err.data)
    } else if (err.name === 'AbortError') {
      console.log('Request was cancelled')
    } else {
      error.value = 'Network error occurred'
    }
  }
}
</script>
```

## Request Cancellation Patterns

### Component-Level Cancellation

```javascript
// All requests are automatically cancelled when component unmounts
const fetcher = useFetcher()

// Manual cancellation of all component requests
const cancelAllRequests = () => {
  fetcher.abort()
}
```

### Specific Request Cancellation

```javascript
// Tag requests with IDs for specific cancellation
const searchUsers = async (query) => {
  // Cancel previous search
  fetcher.abort('search-users')

  const response = await fetcher.get('/users/search', {
    params: { q: query },
    id: 'search-users'
  })
  return response.data
}
```

### Service-Level Control

```javascript
// For long-lived services, manage cancellation manually
const fetcher = useFetcherService()

const longRunningOperation = async () => {
  const controller = new AbortController()

  setTimeout(() => {
    controller.abort() // Cancel after timeout
  }, 30000)

  try {
    const response = await fetcher.post('/long-operation', data, {
      signal: controller.signal
    })
    return response.data
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('Operation timed out')
    }
    throw error
  }
}
```
