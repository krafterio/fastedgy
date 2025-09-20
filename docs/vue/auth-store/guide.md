# Auth Store User Guide

This guide shows you how to use the Auth Store in your Vue.js application with practical examples.

## Complete Login Example

```vue
<template>
  <div>
    <div v-if="authStore.isAuthenticated">
      <p>Welcome, {{ authStore.user.name }}!</p>
      <button @click="logout">Logout</button>
    </div>
    <div v-else>
      <form @submit.prevent="handleLogin">
        <div>
          <label>Email:</label>
          <input v-model="loginData.email" type="email" required />
        </div>
        <div>
          <label>Password:</label>
          <input v-model="loginData.password" type="password" required />
        </div>
        <button type="submit" :disabled="authStore.loading">
          {{ authStore.loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'
import { reactive } from 'vue'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const loginData = reactive({
  email: '',
  password: ''
})

const handleLogin = async () => {
  if (!loginData.email || !loginData.password) return

  const result = await authStore.login(loginData)

  if (!result.success) {
    console.error(result.message || 'Login failed')
    return
  }

  // Redirect after successful login
  router.push({ name: 'Dashboard' })
}

const logout = async () => {
  await authStore.logout()
  router.push({ name: 'Login' })
}
</script>
```

## Router Integration

Protect routes based on authentication status:

```javascript
// In router/index.js
import { useAuthStore } from 'vue-fastedgy/stores/auth'

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Public routes that don't require authentication
  const publicRoutes = ['/login', '/register', '/forgot-password']

  if (publicRoutes.includes(to.path)) {
    return next()
  }

  // Check if route requires authentication
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return next('/login')
  }

  // Handle token refresh if needed
  if (authStore.isTokenExpired && authStore.canRefreshToken) {
    try {
      const success = await authStore.refreshAccessToken()
      if (!success) {
        return next('/login')
      }
    } catch (error) {
      return next('/login')
    }
  }

  next()
})
```

## Registration

Handle user registration:

```vue
<template>
  <form @submit.prevent="handleRegister">
    <div>
      <label>Name:</label>
      <input v-model="registerData.name" type="text" required />
    </div>
    <div>
      <label>Email:</label>
      <input v-model="registerData.email" type="email" required />
    </div>
    <div>
      <label>Password:</label>
      <input v-model="registerData.password" type="password" required />
    </div>
    <div>
      <label>Confirm Password:</label>
      <input v-model="registerData.confirmPassword" type="password" required />
    </div>

    <!-- Optional invitation token -->
    <div v-if="invitationToken">
      <input type="hidden" v-model="registerData.invitationToken" />
    </div>

    <button type="submit" :disabled="authStore.loading">
      {{ authStore.loading ? 'Creating account...' : 'Register' }}
    </button>
  </form>
</template>

<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'
import { reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const invitationToken = route.query.invitation

const registerData = reactive({
  name: '',
  email: '',
  password: '',
  confirmPassword: '',
  invitationToken: invitationToken || undefined
})

const handleRegister = async () => {
  // Basic validation
  if (registerData.password !== registerData.confirmPassword) {
    alert('Passwords do not match')
    return
  }

  try {
    // Register with or without invitation token
    const result = await authStore.register(registerData, registerData.invitationToken)

    if (result.success) {
      // Registration successful, redirect to dashboard
      router.push({ name: 'Dashboard' })
    } else {
      console.error('Registration failed:', result.message)
    }
  } catch (error) {
    console.error('Registration error:', error)
  }
}
</script>
```

## User Status Checking

Verify current user and handle session restoration:

```javascript
// In main.js or app setup
import { useAuthStore } from 'vue-fastedgy/stores/auth'

const authStore = useAuthStore()

// Check if user is still valid on app startup
const initializeAuth = async () => {
  if (authStore.isAuthenticated) {
    try {
      await authStore.checkUser()
    } catch (error) {
      // User session invalid, clear it
      await authStore.logout()
    }
  }
}

// Call during app initialization
initializeAuth()
```

## Loading States

Handle different loading states:

```vue
<template>
  <div class="auth-wrapper">
    <!-- Global loading state -->
    <div v-if="authStore.loading" class="loading-overlay">
      <p>Processing...</p>
    </div>

    <!-- Login form -->
    <div v-else-if="!authStore.isAuthenticated" class="login-form">
      <LoginForm @submit="handleLogin" />
    </div>

    <!-- Authenticated content -->
    <div v-else class="app-content">
      <NavBar />
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'

const authStore = useAuthStore()

const handleLogin = async (credentials) => {
  const result = await authStore.login(credentials)

  if (!result.success) {
    // Handle login error
    showNotification('error', result.message || 'Login failed')
  }
  // Success is handled automatically by reactive state
}
</script>
```

## Conditional Rendering

Show different content based on authentication state:

```vue
<template>
  <nav>
    <!-- Always visible links -->
    <router-link to="/">Home</router-link>

    <!-- Authenticated user links -->
    <template v-if="authStore.isAuthenticated">
      <router-link to="/dashboard">Dashboard</router-link>
      <router-link to="/profile">Profile</router-link>

      <!-- User info -->
      <div class="user-info">
        <span>Welcome, {{ authStore.user.name }}</span>
        <button @click="logout">Logout</button>
      </div>
    </template>

    <!-- Guest links -->
    <template v-else>
      <router-link to="/login">Login</router-link>
      <router-link to="/register">Register</router-link>
    </template>
  </nav>
</template>

<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const logout = async () => {
  await authStore.logout()
  router.push({ name: 'Home' })
}
</script>
```

## Error Handling

Handle authentication errors gracefully:

```javascript
const handleAuthAction = async (action) => {
  try {
    const result = await action()

    if (!result.success) {
      // Handle different types of errors
      switch (result.error) {
        case 'invalid_credentials':
          showError('Invalid email or password')
          break
        case 'account_locked':
          showError('Account is temporarily locked')
          break
        case 'email_not_verified':
          showError('Please verify your email first')
          break
        default:
          showError(result.message || 'Authentication failed')
      }
    }
  } catch (error) {
    // Network or unexpected errors
    showError('Connection error. Please try again.')
    console.error('Auth error:', error)
  }
}

// Usage examples
const login = (credentials) => handleAuthAction(() => authStore.login(credentials))
const register = (userData) => handleAuthAction(() => authStore.register(userData))
```

## Session Timeout Handling

Handle session expiration gracefully:

```vue
<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'
import { onMounted, onUnmounted } from 'vue'

const authStore = useAuthStore()
let sessionCheckInterval

onMounted(() => {
  // Check session every 5 minutes
  sessionCheckInterval = setInterval(async () => {
    if (authStore.isAuthenticated && authStore.isTokenExpired) {
      if (authStore.canRefreshToken) {
        try {
          await authStore.refreshAccessToken()
        } catch (error) {
          // Refresh failed, redirect to login
          await authStore.logout()
          router.push('/login')
          showNotification('info', 'Session expired. Please log in again.')
        }
      } else {
        // No refresh token, log out
        await authStore.logout()
        router.push('/login')
        showNotification('info', 'Session expired. Please log in again.')
      }
    }
  }, 5 * 60 * 1000) // 5 minutes
})

onUnmounted(() => {
  if (sessionCheckInterval) {
    clearInterval(sessionCheckInterval)
  }
})
</script>
```
