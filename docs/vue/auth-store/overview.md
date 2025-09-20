# Auth Store

**Pinia-based authentication state management**

The Auth Store provides a comprehensive authentication solution using Pinia for state management, handling JWT tokens, user sessions, and authentication flows with automatic token refresh and secure storage.

## Key Features

- **JWT Management**: Automatic token handling, refresh, and storage
- **User State**: Centralized user information and permissions
- **Authentication Guards**: Route protection and access control
- **Persistent Sessions**: Secure token storage across browser sessions

## Common Use Cases

- **User Login/Logout**: Handle authentication flows
- **Route Protection**: Protect pages based on authentication status
- **API Authentication**: Automatic token injection in API requests
- **Session Management**: Handle token expiration and refresh

## Quick Example

```vue
<template>
  <div>
    <!-- Authentication status -->
    <div v-if="authStore.isAuthenticated">
      <p>Welcome, {{ authStore.user.name }}!</p>
      <p>Role: {{ authStore.user.role }}</p>
      <button @click="logout">Logout</button>
    </div>

    <div v-else>
      <LoginForm @submit="login" />
    </div>

    <!-- Show loading state -->
    <div v-if="authStore.loading">
      <p>Loading...</p>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'

const authStore = useAuthStore()

const login = async (credentials) => {
  const result = await authStore.login(credentials)
  if (result.success) {
    // Redirect to dashboard
  } else {
    console.error(result.message)
  }
}

const logout = async () => {
  await authStore.logout()
  // Redirect to login page
}
</script>
```

## Store Properties and Methods

### Properties
- `user`: Current user object (null if not authenticated)
- `loading`: Loading state for auth operations
- `isAuthenticated`: Boolean indicating authentication status
- `isTokenExpired`: Boolean indicating if access token is expired
- `canRefreshToken`: Boolean indicating if refresh token is available

### Methods
- `login(credentials)`: Authenticate user and return result object
- `logout()`: Clear user session and tokens
- `register(userData, invitationToken?)`: Register new user
- `refreshAccessToken()`: Refresh expired access token
- `checkUser()`: Verify current user status

## Get Started

Ready to implement authentication? Check out our guides:

[User Guide](guide.md){ .md-button .md-button--primary }
[Advanced Features](advanced.md){ .md-button }
