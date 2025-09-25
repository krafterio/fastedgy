# Auth Store Advanced Features

This guide covers advanced authentication patterns and technical details for power users.

## Token Management

The Auth Store automatically manages JWT tokens with secure storage and refresh:

```javascript
import { useAuthStore } from 'vue-fastedgy'

const authStore = useAuthStore()

// Check token status
console.log('Is authenticated?', authStore.isAuthenticated)
console.log('Token expired?', authStore.isTokenExpired)
console.log('Can refresh?', authStore.canRefreshToken)

// Manual token refresh
const refreshResult = await authStore.refreshAccessToken()
if (refreshResult) {
  console.log('Token refreshed successfully')
} else {
  console.log('Token refresh failed - user logged out')
}

// Check current user data
await authStore.checkUser()
console.log('Current user:', authStore.user)
```

## Token Storage Details

The store uses localStorage for persistence:

```javascript
// Storage keys used by the auth store
const STORAGE_KEYS = {
  ACCESS_TOKEN: 'access_token',
  REFRESH_TOKEN: 'refresh_token'
}

// The store automatically manages these keys
// When login() succeeds:
// - localStorage.setItem('access_token', response.data.access_token)
// - localStorage.setItem('refresh_token', response.data.refresh_token)

// When logout() is called:
// - localStorage.removeItem('access_token')
// - localStorage.removeItem('refresh_token')
```

## Event System Integration

The Auth Store integrates with the Bus system:

```javascript
import { bus } from 'vue-fastedgy'

// Listen for authentication events
bus.addEventListener('auth:logged', (event) => {
  console.log('User logged in successfully')
  // Redirect, load user data, etc.
})

bus.addEventListener('auth:logout', (event) => {
  console.log('User logged out')
  // Clear cached data, redirect to login, etc.
})

// These events are automatically triggered by the store
// No need to manually dispatch them
```

## Router Integration

Protect routes based on authentication status:

```javascript
// In router/index.js
import { useAuthStore } from 'vue-fastedgy'

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Public routes that don't require authentication
  const publicRoutes = ['/login', '/register', '/forgot-password', '/']

  if (publicRoutes.includes(to.path)) {
    return next()
  }

  // Check if route requires authentication
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return next({
      path: '/login',
      query: { redirect: to.fullPath } // Save intended destination
    })
  }

  // Handle token refresh if needed
  if (authStore.isAuthenticated && authStore.isTokenExpired) {
    if (authStore.canRefreshToken) {
      try {
        const refreshed = await authStore.refreshAccessToken()
        if (!refreshed) {
          return next('/login')
        }
      } catch (error) {
        console.error('Token refresh failed:', error)
        return next('/login')
      }
    } else {
      return next('/login')
    }
  }

  next()
})
```

## Route Definitions

Mark routes that require authentication:

```javascript
const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue')
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue')
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  }
]
```

## Advanced Registration Patterns

Handle different registration scenarios:

```javascript
import { useAuthStore } from 'vue-fastedgy'

const authStore = useAuthStore()

// Standard registration
const registerUser = async (userData) => {
  const result = await authStore.register({
    name: userData.name,
    email: userData.email,
    password: userData.password
  })

  if (result.success) {
    console.log('Registration successful, user logged in')
    // User is automatically logged in after registration
  } else {
    console.error('Registration failed:', result.message)
  }
}

// Registration with invitation token
const registerWithInvitation = async (userData, invitationToken) => {
  const result = await authStore.register({
    name: userData.name,
    email: userData.email,
    password: userData.password
  }, invitationToken)

  if (result.success) {
    console.log('Invitation registration successful')
  } else {
    console.error('Invitation registration failed:', result.message)
  }
}

// Check registration status
const handleRegistrationResult = (result) => {
  if (!result.success) {
    switch (result.message) {
      case 'Email déjà enregistré':
        // Show login option instead
        break
      case 'Token d\'invitation invalide':
        // Show invitation error
        break
      default:
        // Show generic error
        break
    }
  }
}
```

## Session Restoration

Restore user session on app startup:

```javascript
// In main.js or App.vue
import { useAuthStore } from 'vue-fastedgy'

const initializeAuth = async () => {
  const authStore = useAuthStore()

  // Check if we have stored tokens
  if (authStore.isAuthenticated) {
    try {
      // Verify tokens are still valid by loading user data
      await authStore.checkUser()
      console.log('Session restored for user:', authStore.user.email)
    } catch (error) {
      // Tokens are invalid, logout
      console.warn('Invalid session, logging out:', error.message)
      await authStore.logout()
    }
  }
}

// Call during app initialization
initializeAuth()
```

## Integration with Fetcher Plugin

The Auth Store works seamlessly with the Fetcher Plugin:

```javascript
// The fetcher plugin automatically:
// 1. Reads tokens from the auth store
// 2. Adds Authorization headers to requests
// 3. Handles 401 responses by refreshing tokens
// 4. Logs out user if refresh fails

// No additional setup required - it works automatically
```

## Error Handling Patterns

Handle different authentication errors:

```javascript
const handleAuthOperation = async (operation) => {
  try {
    const result = await operation()

    if (!result.success) {
      switch (result.message) {
        case 'Email ou mot de passe incorrect':
          showError('Invalid credentials. Please try again.')
          break
        case 'Email déjà enregistré':
          showError('This email is already registered. Try logging in instead.')
          break
        case 'Token d\'invitation invalide':
          showError('Invalid invitation token. Please check your link.')
          break
        default:
          showError(result.message || 'Authentication failed')
      }
    }

    return result
  } catch (error) {
    console.error('Auth operation failed:', error)
    showError('Connection error. Please try again.')
    return { success: false, message: 'Connection error' }
  }
}

// Usage examples
const login = (credentials) => handleAuthOperation(() => authStore.login(credentials))
const register = (userData) => handleAuthOperation(() => authStore.register(userData))
```

## Development and Debugging

Debug authentication state:

```javascript
import { useAuthStore } from 'vue-fastedgy'

// Debug helper for development
window.debugAuth = () => {
  const authStore = useAuthStore()

  console.log('=== Auth Store Debug ===')
  console.log('Authenticated:', authStore.isAuthenticated)
  console.log('User:', authStore.user)
  console.log('Token exists:', !!authStore.token)
  console.log('Token expired:', authStore.isTokenExpired)
  console.log('Can refresh:', authStore.canRefreshToken)
  console.log('Loading state:', authStore.loading)

  // Check localStorage
  console.log('Stored access token:', localStorage.getItem('access_token'))
  console.log('Stored refresh token:', localStorage.getItem('refresh_token'))
}

// Usage in browser console: debugAuth()
```

## Manual Token Management

For advanced use cases where you need direct token control:

```javascript
import { setDefaultAuthorization } from 'vue-fastedgy'

// Manually set authorization for testing
setDefaultAuthorization('your-test-token-here')

// Clear authorization
setDefaultAuthorization(null)

// Note: The auth store automatically manages this
// This is only for special testing scenarios
```
