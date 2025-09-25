# Fetcher Advanced Features

This guide covers the advanced features of the Fetcher for power users and complex use cases.

## Automatic JSON Handling

The fetcher automatically handles JSON serialization and parsing while remaining stream-compatible:

```javascript
const fetcher = useFetcher()

// Objects automatically serialized to JSON
const response = await fetcher.post('/users', {
  name: 'John Doe',          // Auto: Content-Type: application/json
  email: 'john@example.com'  // Auto: JSON.stringify()
})

// JSON responses automatically parsed
const userData = response.data // Auto-parsed from response.json()

// Streams and FormData work unchanged
const formData = new FormData()
formData.append('file', file)
const uploadResponse = await fetcher.post('/upload', formData) // No JSON handling

// File downloads work unchanged
const fileResponse = await fetcher.get('/files/download')
const blob = await fileResponse.blob() // Standard fetch interface

// DELETE requests
await fetcher.delete('/users/123')

// PUT/PATCH with objects
const updatedUser = await fetcher.put('/users/123', { name: 'Updated' })
const patchedUser = await fetcher.patch('/users/123', { status: 'inactive' })
```

**Smart Detection:**
- **Request**: Objects → JSON + `Content-Type` header (FormData, streams untouched)
- **Response**: `application/json` → Auto-parsed to `response.data`
- **Other content types**: Handled normally, `response.data = {}`

## Hook System Integration

The fetcher integrates with a dedicated event bus for global middleware:

```javascript
import { fetchBus } from 'vue-fastedgy'

// Global request hook - triggered before each request
fetchBus.addEventListener('fetch:request', (event) => {
  const { url, options } = event.detail
  console.log('Making request to:', url)

  // Modify request before sending
  options.headers = {
    ...options.headers,
    'X-App-Version': '1.0',
    'X-Request-Time': new Date().toISOString()
  }
})

// Global success hook - triggered after successful requests
fetchBus.addEventListener('fetch:success', (event) => {
  const { url, response, data } = event.detail
  console.log('Request successful:', url, response.status)
  console.log('Response data:', data) // Auto-parsed JSON or {}
})

// Global error hook - triggered on request failures
fetchBus.addEventListener('fetch:error', (event) => {
  const { url, error } = event.detail
  console.error('Request failed:', url, error.message)

  // Log errors to external service
  if (error.response?.status >= 500) {
    // External error tracking service
    console.error('Server error detected:', error)
  }
})
```

## Request Authentication

Add authentication headers globally:

```javascript
import { fetchBus, useAuthStore } from 'vue-fastedgy'

// Setup once in your app
fetchBus.addEventListener('fetch:request', (event) => {
  const { options } = event.detail
  const authStore = useAuthStore()

  // Add auth token to all requests
  if (authStore.token) {
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${authStore.token}`
    }
  }
})
```

## Request and Response Logging

Log all API interactions for debugging:

```javascript
import { fetchBus } from 'vue-fastedgy'

// Request logging
fetchBus.addEventListener('fetch:request', (event) => {
  const { url, options } = event.detail

  console.group(`📤 ${options.method || 'GET'} ${url}`)

  if (options.body) {
    console.log('Body:', options.body)
  }

  if (options.params) {
    console.log('Params:', options.params)
  }

  console.log('Headers:', options.headers)
  console.groupEnd()
})

// Response logging
fetchBus.addEventListener('fetch:success', (event) => {
  const { url, response, data } = event.detail

  console.group(`📥 ${response.status} ${url}`)
  console.log('Data:', data)
  console.log('Headers:', Object.fromEntries(response.headers.entries()))
  console.groupEnd()
})

// Error logging
fetchBus.addEventListener('fetch:error', (event) => {
  const { url, error } = event.detail

  console.group(`❌ ERROR ${url}`)
  console.error('Error:', error.message)

  if (error.response) {
    console.log('Status:', error.response.status)
    console.log('Data:', error.data)
  }

  console.groupEnd()
})
```

## HttpError Handling

Handle different HTTP error types:

```javascript
import { HttpError } from 'vue-fastedgy'

const handleApiCall = async () => {
  try {
    const response = await fetcher.post('/api/users', userData)
    console.log('User created:', response.data)
  } catch (error) {
    if (error instanceof HttpError) {
      const status = error.response.status

      switch (status) {
        case 400:
          console.error('Bad Request:', error.data)
          break
        case 401:
          console.error('Unauthorized - redirecting to login')
          // Handle auth error
          break
        case 403:
          console.error('Forbidden - insufficient permissions')
          break
        case 422:
          console.error('Validation Error:', error.data.detail)
          break
        case 500:
          console.error('Server Error:', error.message)
          break
        default:
          console.error('HTTP Error:', status, error.message)
      }
    } else if (error.name === 'AbortError') {
      console.log('Request was cancelled')
    } else {
      console.error('Network Error:', error.message)
    }
  }
}
```

## Service-Level Integration

Use the hook system in service classes:

```javascript
import { fetchBus, useFetcherService } from 'vue-fastedgy'

class ApiService {
  constructor() {
    this.fetcher = useFetcherService()
    this.setupHooks()
  }

  setupHooks() {
    // Service-specific request handling
    fetchBus.addEventListener('fetch:request', (event) => {
      const { url, options } = event.detail

      // Add service identifier to requests from this service
      if (this.isMyRequest(url)) {
        options.headers = {
          ...options.headers,
          'X-Service': 'ApiService'
        }
      }
    })
  }

  isMyRequest(url) {
    // Logic to identify requests from this service
    return url.startsWith('/api/')
  }

  async getUsers() {
    return this.fetcher.get('/api/users')
  }
}
```

## AbortController Management

Advanced abort control patterns:

```javascript
const fetcher = useFetcher()

// Abort specific requests by ID
const searchUsers = async (query) => {
  // Cancel previous search if still running
  fetcher.abort('user-search')

  const response = await fetcher.get('/users/search', {
    params: { q: query },
    id: 'user-search' // This ID can be used to abort this specific request
  })

  return response.data
}

// Abort multiple related requests
const loadDashboard = async () => {
  // Cancel any previous dashboard loading
  fetcher.abort('dashboard-users')
  fetcher.abort('dashboard-stats')
  fetcher.abort('dashboard-notifications')

  const [users, stats, notifications] = await Promise.all([
    fetcher.get('/users', { id: 'dashboard-users' }),
    fetcher.get('/stats', { id: 'dashboard-stats' }),
    fetcher.get('/notifications', { id: 'dashboard-notifications' })
  ])

  return { users: users.data, stats: stats.data, notifications: notifications.data }
}

// Component unmount automatically aborts all requests
// This is handled by useFetcher() automatically
```

## Custom Headers and Options

Advanced request configuration:

```javascript
const fetcher = useFetcher()

// Custom headers for specific requests
const response = await fetcher.post('/api/upload', formData, {
  headers: {
    'X-Upload-Type': 'avatar',
    'X-Max-Size': '5MB'
  }
})

// Custom fetch options
const streamResponse = await fetcher.get('/api/download', {
  // Disable automatic JSON parsing for binary data
  headers: { 'Accept': 'application/octet-stream' }
})

// Custom timeout (using AbortController)
const controller = new AbortController()
setTimeout(() => controller.abort(), 10000) // 10 second timeout

try {
  const response = await fetcher.get('/api/slow-endpoint', {
    signal: controller.signal
  })
} catch (error) {
  if (error.name === 'AbortError') {
    console.log('Request timed out after 10 seconds')
  }
}
```
