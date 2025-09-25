# Routers User Guide

This guide shows you how to use the router utilities in real Vue.js applications with practical examples and patterns.

## Vue Component Usage

```vue
<template>
  <div>
    <!-- Search form that updates URL -->
    <form @submit.prevent="search">
      <input v-model="searchQuery" placeholder="Search users..." />
      <button type="submit">Search</button>
    </form>

    <!-- Filter controls -->
    <div class="filters">
      <select v-model="statusFilter" @change="updateFilters">
        <option value="">All Status</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
      </select>

      <select v-model="roleFilter" @change="updateFilters">
        <option value="">All Roles</option>
        <option value="admin">Admin</option>
        <option value="user">User</option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { replaceRouteQuery, restoreRouteQuery } from 'vue-fastedgy'
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const searchQuery = ref('')
const statusFilter = ref('')
const roleFilter = ref('')

// Restore state from URL on component mount
onMounted(() => {
  searchQuery.value = restoreRouteQuery('q', route, 'search', '')
  statusFilter.value = restoreRouteQuery('status', route, 'search', '')
  roleFilter.value = restoreRouteQuery('role', route, 'search', '')
})

const search = () => {
  replaceRouteQuery(router, {
    q: searchQuery.value || undefined,
    page: undefined // Reset pagination on new search
  }, route, 'search')
}

const updateFilters = () => {
  replaceRouteQuery(router, {
    status: statusFilter.value || undefined,
    role: roleFilter.value || undefined,
    page: undefined // Reset pagination on filter change
  }, route, 'search')
}
</script>
```

## Login Redirect Flow

Handle authentication redirects properly:

```vue
<!-- LoginPage.vue -->
<script setup>
import { addRedirect, getRedirect, useAuthStore } from 'vue-fastedgy'
import { useRoute, useRouter } from 'vue-router'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

const handleLogin = async (credentials) => {
  const result = await authStore.login(credentials)

  if (result.success) {
    // Get intended destination or default to dashboard
    const redirectTo = getRedirect(route, { name: 'Dashboard' })
    router.push(redirectTo)
  } else {
    console.error(result.message)
  }
}
</script>
```

```javascript
// In router guards
import { addRedirect, useAuthStore } from 'vue-fastedgy'

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    // Save intended destination
    const loginRoute = addRedirect(from, { name: 'Login' })
    next(loginRoute)
  } else {
    next()
  }
})
```

## Advanced Filter Management

Handle complex filter state with URL synchronization:

```vue
<template>
  <div class="data-table">
    <!-- Filter controls -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>Search:</label>
        <input v-model="filters.search" @input="updateFiltersDebounced" />
      </div>

      <div class="filter-group">
        <label>Date Range:</label>
        <input v-model="filters.dateFrom" type="date" @change="updateFilters" />
        <input v-model="filters.dateTo" type="date" @change="updateFilters" />
      </div>

      <div class="filter-group">
        <label>Categories:</label>
        <select v-model="filters.categories" multiple @change="updateFilters">
          <option v-for="cat in availableCategories" :key="cat.id" :value="cat.id">
            {{ cat.name }}
          </option>
        </select>
      </div>

      <button @click="clearFilters">Clear All</button>
    </div>

    <!-- Results -->
    <div class="results">
      <div v-for="item in filteredResults" :key="item.id">
        {{ item.name }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { replaceRouteQuery, restoreRouteQuery } from 'vue-fastedgy'
import { reactive, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { debounce } from 'lodash-es'

const route = useRoute()
const router = useRouter()

const filters = reactive({
  search: '',
  dateFrom: '',
  dateTo: '',
  categories: []
})

const filteredResults = ref([])
const availableCategories = ref([])

// Restore filters from URL on mount
onMounted(() => {
  filters.search = restoreRouteQuery('search', route, 'filters', '')
  filters.dateFrom = restoreRouteQuery('dateFrom', route, 'filters', '')
  filters.dateTo = restoreRouteQuery('dateTo', route, 'filters', '')
  filters.categories = restoreRouteQuery('categories', route, 'filters', [], 'object')

  // Initial data load
  loadData()
})

// Update URL when filters change
const updateFilters = () => {
  const filterData = {
    search: filters.search || undefined,
    dateFrom: filters.dateFrom || undefined,
    dateTo: filters.dateTo || undefined,
    categories: filters.categories.length > 0 ? filters.categories : undefined
  }

  replaceRouteQuery(router, filterData, route, 'filters')
  loadData()
}

// Debounced update for search input
const updateFiltersDebounced = debounce(updateFilters, 300)

const clearFilters = () => {
  Object.keys(filters).forEach(key => {
    if (Array.isArray(filters[key])) {
      filters[key] = []
    } else {
      filters[key] = ''
    }
  })
  updateFilters()
}

const loadData = async () => {
  // Load data based on current filters
  const response = await fetch('/api/data?' + new URLSearchParams(filters))
  filteredResults.value = await response.json()
}

// Watch for external URL changes (browser back/forward)
watch(() => route.query, () => {
  // Re-sync filters from URL
  filters.search = restoreRouteQuery('search', route, 'filters', '')
  filters.dateFrom = restoreRouteQuery('dateFrom', route, 'filters', '')
  filters.dateTo = restoreRouteQuery('dateTo', route, 'filters', '')
  filters.categories = restoreRouteQuery('categories', route, 'filters', [], 'object')

  loadData()
})
</script>
```

## Pagination with URL State

Keep pagination state in the URL:

```vue
<template>
  <div>
    <!-- Results -->
    <div class="results">
      <div v-for="item in currentPageItems" :key="item.id">
        {{ item.name }}
      </div>
    </div>

    <!-- Pagination -->
    <div class="pagination">
      <button
        @click="goToPage(currentPage - 1)"
        :disabled="currentPage <= 1"
      >
        Previous
      </button>

      <span>Page {{ currentPage }} of {{ totalPages }}</span>

      <button
        @click="goToPage(currentPage + 1)"
        :disabled="currentPage >= totalPages"
      >
        Next
      </button>
    </div>
  </div>
</template>

<script setup>
import { replaceRouteQuery, restoreRouteQuery } from 'vue-fastedgy'
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const items = ref([])
const currentPage = ref(1)
const itemsPerPage = 10

const totalPages = computed(() => Math.ceil(items.value.length / itemsPerPage))

const currentPageItems = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return items.value.slice(start, end)
})

onMounted(() => {
  // Restore page from URL
  currentPage.value = parseInt(restoreRouteQuery('page', route, 'pagination', '1')) || 1
  loadData()
})

const goToPage = (page) => {
  if (page < 1 || page > totalPages.value) return

  currentPage.value = page

  // Update URL
  replaceRouteQuery(router, {
    page: page > 1 ? page : undefined
  }, route, 'pagination')
}

const loadData = async () => {
  // Load data for current page
  const response = await fetch(`/api/items?page=${currentPage.value}&limit=${itemsPerPage}`)
  items.value = await response.json()
}
</script>
```

## Multi-Step Form with URL State

Save form progress in URL for multi-step forms:

```vue
<template>
  <div class="multi-step-form">
    <!-- Step indicators -->
    <div class="steps">
      <div
        v-for="(step, index) in steps"
        :key="index"
        :class="{ active: currentStep === index, completed: index < currentStep }"
      >
        {{ step.title }}
      </div>
    </div>

    <!-- Step content -->
    <component
      :is="steps[currentStep].component"
      v-model="formData[steps[currentStep].key]"
      @next="nextStep"
      @previous="previousStep"
    />
  </div>
</template>

<script setup>
import { replaceRouteQuery, restoreRouteQuery } from 'vue-fastedgy'
import { reactive, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const steps = [
  { title: 'Basic Info', component: 'BasicInfoStep', key: 'basicInfo' },
  { title: 'Contact', component: 'ContactStep', key: 'contact' },
  { title: 'Preferences', component: 'PreferencesStep', key: 'preferences' },
  { title: 'Review', component: 'ReviewStep', key: 'review' }
]

const currentStep = ref(0)
const formData = reactive({
  basicInfo: {},
  contact: {},
  preferences: {},
  review: {}
})

onMounted(() => {
  // Restore step and form data from URL
  currentStep.value = parseInt(restoreRouteQuery('step', route, 'form', '0')) || 0

  const savedData = restoreRouteQuery('data', route, 'form', {}, 'object')
  if (savedData && typeof savedData === 'object') {
    Object.assign(formData, savedData)
  }
})

const nextStep = () => {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
    updateURL()
  }
}

const previousStep = () => {
  if (currentStep.value > 0) {
    currentStep.value--
    updateURL()
  }
}

const updateURL = () => {
  replaceRouteQuery(router, {
    step: currentStep.value > 0 ? currentStep.value : undefined,
    data: Object.keys(formData).some(key =>
      Object.keys(formData[key]).length > 0
    ) ? formData : undefined
  }, route, 'form')
}

// Auto-save form data when it changes
watch(formData, () => {
  updateURL()
}, { deep: true })
</script>
```
