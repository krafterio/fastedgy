# Fetcher Plugin

**Authentication and configuration plugin for HTTP requests**

The Fetcher Plugin provides automatic authentication, token refresh, and global configuration for all HTTP requests made with `useFetcher()`. It handles JWT tokens, automatic retry on 401 errors, and sets up the base URL configuration.

## Key Features

- **Automatic Authentication**: Injects JWT tokens into all requests
- **Token Refresh**: Automatically refreshes expired tokens
- **Request Retry**: Retries failed requests after token refresh
- **Base URL Configuration**: Sets up global API base URL
- **Auth Store Integration**: Works seamlessly with the auth store

## Common Use Cases

- **Global Authentication**: Automatic JWT token handling for all requests
- **API Configuration**: Set base URL and default headers
- **Token Management**: Automatic refresh and logout on auth failures
- **Request Middleware**: Global request/response interceptors

## Usage in Components

**Always use `useFetcher()` in components, never access plugin directly:**

```javascript
import { useFetcher } from 'vue-fastedgy'

const fetcher = useFetcher()
const users = await fetcher.get('/users') // Automatically authenticated
```

The plugin works behind the scenes to:
- Add authentication headers automatically
- Refresh tokens when they expire
- Retry failed requests after token refresh
- Handle base URL resolution

## Get Started

Ready to install the plugin? Check out the setup guide:

[Setup Guide](setup.md){ .md-button .md-button--primary }
