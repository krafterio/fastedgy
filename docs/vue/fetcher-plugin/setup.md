# Fetcher Plugin Setup

This guide shows how to install and configure the Fetcher Plugin in your Vue.js application.

## Installation

```javascript
// In main.js
import { createFetcher } from 'vue-fastedgy/plugins/fetcher'
import { createApp } from 'vue'
import App from './App.vue'

const app = createApp(App)
const fetcher = createFetcher()

app.use(fetcher)
app.mount('#app')
```

## Environment Configuration

The plugin automatically reads environment variables:

```bash
# .env
VITE_API_URL=https://api.example.com
```

The plugin will automatically set this as the base URL for all requests.

## Configuration Functions

The plugin exports utility functions for global configuration:

```javascript
import {
  setDefaultBaseUrl,
  setDefaultHeaders,
  setDefaultAuthorization,
  absoluteUrl
} from 'vue-fastedgy/plugins/fetcher'

// Set base URL (usually set via environment variables)
setDefaultBaseUrl('https://api.example.com')

// Set default headers
setDefaultHeaders({
  'X-Custom-Header': 'value',
  'X-App-Version': '1.0.0'
})

// Set authorization token
setDefaultAuthorization('your-jwt-token')

// Convert relative URL to absolute
const fullUrl = absoluteUrl('/users')
// Returns: 'https://api.example.com/users'
```

## Advanced Configuration

### Custom Headers Per Environment

```javascript
import { setDefaultHeaders } from 'vue-fastedgy/plugins/fetcher'

const headers = {
  'X-App-Version': '1.0.0'
}

// Add environment-specific headers
if (process.env.NODE_ENV === 'development') {
  headers['X-Debug'] = 'true'
}

if (process.env.VITE_ENVIRONMENT === 'staging') {
  headers['X-Staging'] = 'true'
}

setDefaultHeaders(headers)
```

### Dynamic Base URL

```javascript
import { setDefaultBaseUrl } from 'vue-fastedgy/plugins/fetcher'

// Set different base URLs based on environment
const getBaseUrl = () => {
  switch (process.env.NODE_ENV) {
    case 'development':
      return 'http://localhost:8000'
    case 'staging':
      return 'https://staging-api.example.com'
    case 'production':
      return 'https://api.example.com'
    default:
      return 'http://localhost:8000'
  }
}

setDefaultBaseUrl(getBaseUrl())
```

## Integration with Auth Store

The plugin automatically integrates with the Auth Store:

```javascript
// The plugin automatically:
// 1. Reads tokens from localStorage on startup
// 2. Updates headers when auth store login/logout occurs
// 3. Handles token refresh automatically
// 4. Redirects to login on auth failures

// No manual configuration needed - it works automatically!
```

## Troubleshooting

### Base URL Issues

```javascript
import { absoluteUrl } from 'vue-fastedgy/plugins/fetcher'

// Check if base URL is configured correctly
console.log('Base URL test:', absoluteUrl('/test'))
// Should output: 'https://your-api.com/test'
```

### Headers Not Being Added

```javascript
import { setDefaultHeaders } from 'vue-fastedgy/plugins/fetcher'

// Verify headers are set
setDefaultHeaders({ 'X-Test': 'value' })

// Check in network tab that requests include the header
```

### Authentication Not Working

1. Verify the Auth Store is properly configured
2. Check that tokens are stored in localStorage
3. Ensure the plugin is installed before making any requests

```javascript
// Debug auth headers
import { setDefaultAuthorization } from 'vue-fastedgy/plugins/fetcher'

const token = localStorage.getItem('access_token')
console.log('Token:', token)

if (token) {
  setDefaultAuthorization(token)
}
```
