# Vue.js Integration - Troubleshooting

Common issues and solutions when working with Vue-FastEdgy integration.

## CORS Issues

If you encounter CORS errors, ensure your FastEdgy backend is configured to accept requests from your Vue.js development server:

```python
# In your FastEdgy main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your Vue dev server URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Environment Variable Not Loading

Make sure your `.env` file is in the project root and that `BASE_URL` is properly set:

```bash
# Correct format
BASE_URL=http://localhost:8000/api

# Not like this
BASE_URL="http://localhost:8000/api"  # Remove quotes
```

## Module Not Found

If you get module import errors, ensure the package was installed correctly:

```bash
npm ls vue-fastedgy
# Should show the package in the dependency tree
```

## Authentication Issues

### Token Not Persisted

If user sessions are not persisting across browser refreshes:

```javascript
// Check if localStorage is working
console.log('Token:', localStorage.getItem('access_token'))

// Clear storage if corrupted
localStorage.removeItem('access_token')
localStorage.removeItem('refresh_token')
```

### Login Method Not Working

Ensure the auth store login method is called correctly:

```javascript
const result = await authStore.login(loginData)

if (!result.success) {
  console.error('Login failed:', result.message)
  // Handle error appropriately
}
```

## Network Issues

### API Calls Failing

Check that your `BASE_URL` environment variable matches your FastEdgy backend:

```bash
# Development
BASE_URL=http://localhost:8000/api

# Make sure the /api suffix is included
# FastEdgy typically serves API routes under /api
```

### Request Timeout

If requests are timing out, you can configure the fetcher timeout:

```javascript
// This is typically handled automatically by vue-fastedgy
// But check your network and backend responsiveness
```

## Build Issues

### Package Not Found During Build

Ensure vue-fastedgy is installed as a dependency (not devDependency):

```json
{
  "dependencies": {
    "vue-fastedgy": "git+ssh://git@github.com:krafterio/vue-fastedgy.git#main"
  }
}
```

### TypeScript Errors

If using TypeScript, make sure type definitions are available:

```bash
# Check if types are being resolved
npx tsc --noEmit
```

## Performance Issues

### Fetcher Memory Leaks

Make sure to properly clean up subscriptions and watchers:

```javascript
import { onUnmounted } from 'vue'

onUnmounted(() => {
  // Clean up any subscriptions or watchers
})
```

## Getting Help

If you're still experiencing issues:

1. Check the browser console for error messages
2. Verify your FastEdgy backend is running and accessible
3. Test API endpoints directly (using Postman or curl)
4. Check the [FastEdgy backend documentation](../index.md) for backend setup

Ready to build amazing applications with Vue.js and FastEdgy!
