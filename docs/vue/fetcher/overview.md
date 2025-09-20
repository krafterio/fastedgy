# Fetcher

**Lightweight wrapper over native fetch with Vue.js integration**

The Fetcher provides a thin, composable layer over the native fetch API, designed specifically for Vue.js applications. It maintains full compatibility with the standard fetch interface while adding Vue lifecycle integration, simplified cancellation, and a powerful hook system via event bus.

## Key Features

- **Native Fetch Compatible**: Same interface as standard fetch API
- **Automatic JSON Handling**: Auto-serialize objects to JSON, auto-parse JSON responses
- **Stream Compatible**: Works seamlessly with file uploads, downloads, and streams
- **Vue Composition API**: Seamless integration with Vue lifecycle
- **Automatic Cancellation**: Auto-abort requests on component unmount
- **Hook System**: Global event bus for request/response middleware
- **Simplified Abort Control**: Easy request cancellation management
- **Lightweight**: Minimal overhead over native fetch

## Common Use Cases

- **Vue Component Integration**: Fetch data with automatic cleanup
- **Request Middleware**: Global hooks for authentication, logging, error handling
- **File Downloads**: Handle blob responses and file operations
- **Component-Scoped Requests**: Automatic cancellation on unmount

## Quick Example

```javascript
import { useFetcher } from 'vue-fastedgy/composables/fetcher'

const fetcher = useFetcher()

// REST methods with automatic JSON handling
const getResponse = await fetcher.get('/users')
const users = getResponse.data // Auto-parsed JSON

// POST with automatic JSON serialization
const postResponse = await fetcher.post('/users', {
  name: 'John Doe',
  email: 'john@example.com'
})

// Query parameters (enhanced)
const filteredResponse = await fetcher.get('/users', {
  params: { active: true, limit: 10 },
  id: 'filter-users' // Optional ID for targeted abort control
})

// Other REST methods
const updatedUser = await fetcher.put('/users/123', userData)
const patchedUser = await fetcher.patch('/users/123', { name: 'New Name' })
await fetcher.delete('/users/123')

// Manual abort control
fetcher.abort() // Abort all component requests
fetcher.abort('users-list') // Abort specific request by ID (must match options.id)
```

## Get Started

Ready to use the Fetcher in your application? Check out our guides:

[User Guide](guide.md){ .md-button .md-button--primary }
[Advanced Features](advanced.md){ .md-button }
