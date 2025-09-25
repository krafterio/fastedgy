# Bus User Guide

This guide shows you how to use the Bus system in real Vue.js applications with practical examples and patterns.

## Component Integration

Here's a complete example showing how to build a notification system using the Bus:

```vue
<template>
  <div>
    <div v-if="notifications.length > 0" class="space-y-2">
      <div
        v-for="notification in notifications"
        :key="notification.id"
        class="p-3 bg-blue-50 border border-blue-200 rounded"
      >
        {{ notification.message }}
      </div>
    </div>

    <button @click="sendNotification">
      Send Test Notification
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { bus, useBus } from 'vue-fastedgy'

const notifications = ref([])

const handleNotification = (event) => {
  const data = event.detail
  notifications.value.push({
    id: Date.now(),
    message: data.message
  })

  // Auto-remove after 3 seconds
  setTimeout(() => {
    notifications.value = notifications.value.filter(n => n.id !== data.id)
  }, 3000)
}

const sendNotification = () => {
  bus.trigger('notification:show', {
    id: Date.now(),
    message: 'This is a test notification'
  })
}

// Automatic cleanup on component unmount
useBus(bus, 'notification:show', handleNotification)
</script>
```

## Manual Event Handling

For more control, you can handle events manually using Vue's lifecycle hooks:

```javascript
import { bus } from 'vue-fastedgy'
import { onMounted, onBeforeUnmount } from 'vue'

const handleEvent = (event) => {
  console.log('Event data:', event.detail)
}

onMounted(() => {
  bus.addEventListener('my:event', handleEvent)
})

onBeforeUnmount(() => {
  bus.removeEventListener('my:event', handleEvent)
})
```

## Event Patterns

### Request/Response Pattern

```javascript
// Component A - Request data
bus.trigger('data:request', { userId: 123 })

// Component B - Respond with data
useBus(bus, 'data:request', async (event) => {
  const { userId } = event.detail
  const userData = await fetchUser(userId)
  bus.trigger('data:response', userData)
})

// Component A - Handle response
useBus(bus, 'data:response', (event) => {
  console.log('Received user data:', event.detail)
})
```

### Async Coordination

```javascript
// Wait for multiple services to complete
await bus.triggerAndWait('app:initialize', {
  modules: ['auth', 'config', 'cache']
})

// Each service handles initialization
useBus(bus, 'app:initialize', async (event) => {
  await initializeMyModule()
  console.log('Module initialized')
})
```
