# Basic Usage

Once Vue-FastEdgy is installed and configured, you can start using its features in your Vue components:

## Using the Fetcher

```vue
<template>
  <div>
    <h2>Users List</h2>
    <div v-if="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <ul v-else>
      <li v-for="user in users" :key="user.id">
        {{ user.name }} - {{ user.email }}
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useFetcher } from 'vue-fastedgy/composables/fetcher'

const fetcher = useFetcher()
const users = ref([])
const loading = ref(false)
const error = ref(null)

const fetchUsers = async () => {
  try {
    loading.value = true
    error.value = null
    const response = await fetcher.get('/users')
    users.value = response.data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchUsers()
})
</script>
```

## Using the Auth Store

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
        <button type="submit" :disabled="loading">
          {{ loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from 'vue-fastedgy/stores/auth'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const loginData = reactive({
  email: '',
  password: ''
})

const loading = ref(false)

const handleLogin = async () => {
  if (!loginData.email || !loginData.password) return

  loading.value = true
  try {
    const result = await authStore.login(loginData)

    if (!result.success) {
      console.error(result.message || 'Login failed')
      return
    }

    // Redirect after successful login
    router.push({ name: 'Dashboard' })
  } catch (error) {
    console.error('Login error:', error)
  } finally {
    loading.value = false
  }
}

const logout = async () => {
  await authStore.logout()
  router.push({ name: 'Login' })
}
</script>
```

## Next Steps

Now that Vue-FastEdgy is set up, explore the available features:

- **[Bus](bus/overview.md)** - Event bus for component communication
- **[Fetcher](fetcher/overview.md)** - HTTP client for API communication
- **[Fetcher Plugin](fetcher-plugin/overview.md)** - Vue plugin for global fetcher access
- **[Fetcher Directive](fetcher-directive/overview.md)** - Vue directive for declarative data fetching
- **[Metadata Store](metadata-store/overview.md)** - Dynamic form and UI generation
- **[Auth Store](auth-store/overview.md)** - Authentication state management
- **[Validation Helpers](validations/overview.md)** - API error formatting utilities
- **[Router Helpers](routers/overview.md)** - Route manipulation utilities
- **[Logger](logger/overview.md)** - Console logging management

Ready to build amazing applications with Vue.js and FastEdgy!
