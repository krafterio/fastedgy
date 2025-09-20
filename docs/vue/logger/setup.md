# Logger Setup Guide

This guide shows you how to configure and use the logger in your Vue.js application.

## Vue Application Setup

```javascript
// main.js
import { createApp } from 'vue'
import { initializeLogger, LOG_LEVELS } from 'vue-fastedgy/utils/logger'
import App from './App.vue'

// Configure logging based on environment
const logLevel = process.env.NODE_ENV === 'production'
  ? LOG_LEVELS.ERROR  // Only errors in production
  : LOG_LEVELS.DEBUG  // All logs in development

initializeLogger(logLevel)

const app = createApp(App)
app.mount('#app')
```

## Environment-Based Configuration

### Development vs Production

```javascript
// Recommended setup
const getLogLevel = () => {
  switch (process.env.NODE_ENV) {
    case 'production':
      return LOG_LEVELS.NONE    // Disable all logs in production
    case 'staging':
      return LOG_LEVELS.ERROR   // Only errors in staging
    case 'test':
      return LOG_LEVELS.NONE    // Disable logs during testing
    default:
      return LOG_LEVELS.DEBUG   // Full logging in development
  }
}

initializeLogger(getLogLevel())
```

### Environment Variable Control

```javascript
// Allow runtime log level control via environment variable
const LOG_LEVEL_MAP = {
  'none': LOG_LEVELS.NONE,
  'error': LOG_LEVELS.ERROR,
  'warning': LOG_LEVELS.WARNING,
  'info': LOG_LEVELS.INFO,
  'debug': LOG_LEVELS.DEBUG
}

const envLogLevel = process.env.VITE_LOG_LEVEL || 'info'
const logLevel = LOG_LEVEL_MAP[envLogLevel.toLowerCase()] || LOG_LEVELS.INFO

initializeLogger(logLevel)
```

## Usage in Components

Once initialized, use console methods normally throughout your application:

```vue
<template>
  <div>
    <button @click="handleClick">Test Logging</button>
    <div v-if="data">{{ data }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useFetcher } from 'vue-fastedgy/composables/fetcher'

const fetcher = useFetcher()
const data = ref(null)

const handleClick = async () => {
  console.debug('Button clicked, starting request...')

  try {
    console.info('Fetching data from users')
    const response = await fetcher.get('/users')

    data.value = response.data
    console.info('Data loaded successfully:', data.value.length, 'users')
  } catch (error) {
    console.error('Failed to fetch users:', error)
    console.warn('Using fallback data instead')
    data.value = []
  }
}
</script>
```

## Service Classes

Use logging in service classes:

```javascript
// services/UserService.js
import { useFetcherService } from 'vue-fastedgy/composables/fetcher'

export class UserService {
  constructor() {
    this.fetcher = useFetcherService()
  }

  async getUsers(filters = {}) {
    console.debug('UserService.getUsers called with filters:', filters)

    try {
      const response = await this.fetcher.get('/users', { params: filters })
      console.info(`Loaded ${response.data.length} users`)
      return response.data
    } catch (error) {
      console.error('UserService.getUsers failed:', error)
      throw error
    }
  }

  async createUser(userData) {
    console.debug('UserService.createUser called with:', userData)

    try {
      const response = await this.fetcher.post('/users', userData)
      console.info('User created successfully:', response.data.id)
      return response.data
    } catch (error) {
      console.error('UserService.createUser failed:', error)
      throw error
    }
  }
}
```

## Debugging Patterns

### API Request Logging

```javascript
// Log API requests and responses
const apiCall = async (method, url, data = null) => {
  console.debug(`API ${method.toUpperCase()} ${url}`, data)

  try {
    const response = await fetcher[method.toLowerCase()](url, data)
    console.info(`API ${method.toUpperCase()} ${url} success:`, response.status)
    return response
  } catch (error) {
    console.error(`API ${method.toUpperCase()} ${url} failed:`, error)
    throw error
  }
}
```

### Component Lifecycle Logging

```vue
<script setup>
import { onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps(['userId'])

onMounted(() => {
  console.debug('UserProfile component mounted, userId:', props.userId)
  loadUserData()
})

onBeforeUnmount(() => {
  console.debug('UserProfile component unmounting')
})

watch(() => props.userId, (newId, oldId) => {
  console.debug('UserProfile userId changed:', { from: oldId, to: newId })
  if (newId) {
    loadUserData()
  }
})

const loadUserData = async () => {
  console.info('Loading user data for ID:', props.userId)
  // ... fetch logic
}
</script>
```

### Error Boundary Logging

```javascript
// Global error handler
app.config.errorHandler = (error, instance, info) => {
  console.error('Vue error caught:', error)
  console.error('Component instance:', instance)
  console.error('Error info:', info)

  // Also log to external service in production
  if (process.env.NODE_ENV === 'production') {
    // sendToErrorTracking(error, instance, info)
  }
}
```

## Advanced Configuration

### Conditional Logging by Module

```javascript
// Create module-specific loggers
const createModuleLogger = (moduleName) => {
  const isEnabled = localStorage.getItem(`debug:${moduleName}`) === 'true'

  return {
    debug: (...args) => isEnabled && console.debug(`[${moduleName}]`, ...args),
    info: (...args) => isEnabled && console.info(`[${moduleName}]`, ...args),
    warn: (...args) => isEnabled && console.warn(`[${moduleName}]`, ...args),
    error: (...args) => console.error(`[${moduleName}]`, ...args) // Always log errors
  }
}

// Usage
const authLogger = createModuleLogger('Auth')
const apiLogger = createModuleLogger('API')

// Enable specific modules in browser console:
// localStorage.setItem('debug:Auth', 'true')
```

### Performance Logging

```javascript
// Performance measurement utilities
const perfLogger = {
  start(label) {
    console.debug(`⏱️ Starting: ${label}`)
    console.time(label)
  },

  end(label) {
    console.timeEnd(label)
    console.debug(`⏱️ Finished: ${label}`)
  },

  mark(label, ...data) {
    console.debug(`📍 Mark: ${label}`, ...data)
  }
}

// Usage in components
const loadData = async () => {
  perfLogger.start('loadData')

  try {
    perfLogger.mark('starting API call')
    const response = await fetcher.get('/data')

    perfLogger.mark('processing data', response.data.length, 'items')
    const processed = processData(response.data)

    perfLogger.end('loadData')
    return processed
  } catch (error) {
    perfLogger.end('loadData')
    throw error
  }
}
```

## Testing Configuration

```javascript
// In test setup files
import { initializeLogger, LOG_LEVELS } from 'vue-fastedgy/utils/logger'

// Disable all logging during tests to keep output clean
beforeAll(() => {
  initializeLogger(LOG_LEVELS.NONE)
})

// Or only allow errors for debugging test failures
beforeAll(() => {
  initializeLogger(LOG_LEVELS.ERROR)
})
```

## Browser Console Tips

Once the logger is initialized, you can still control it from browser console:

```javascript
// In browser console during development:

// Temporarily enable all logging
initializeLogger(LOG_LEVELS.DEBUG)

// Disable all logging
initializeLogger(LOG_LEVELS.NONE)

// Check current environment
console.log('NODE_ENV:', process.env.NODE_ENV)
```
