# User guide

## Creating a specialized service

Always create a specialized service rather than using `useApiService` directly:

```javascript
// services/tasks.js
import { useApiService } from 'vue-fastedgy/composables/api'

export function useTasksService() {
    return useApiService('tasks')
}
```

## Using in a component

```javascript
import { useTasksService } from '@/services/tasks'

export default {
    setup() {
        const tasksService = useTasksService()

        const loadTasks = async () => {
            const response = await tasksService.list({
                page: 1,
                size: 20,
                orderBy: ['-created_at']
            })
            return response.data
        }

        return { loadTasks }
    }
}
```

## Available operations

### List with options

```javascript
await tasksService.list({
    page: 1,
    size: 20,
    fields: ['id', 'title', 'completed'],
    orderBy: ['-created_at', 'title'],
    filter: { completed: false }
})
```

### Get by ID

```javascript
await tasksService.get(123, {
    fields: ['id', 'title', 'description']
})
```

### Create

```javascript
await tasksService.create({
    title: 'New task',
    description: 'Task description'
})
```

### Update

```javascript
await tasksService.update(123, {
    completed: true,
    completed_at: new Date().toISOString()
})
```

### Delete

```javascript
await tasksService.delete(123)
```

### Export

```javascript
await tasksService.export({
    format: 'csv',
    fields: ['id', 'title', 'created_at']
})
```

## Admin service

For administrative operations:

```javascript
// services/admin-users.js
export function useAdminUsersService() {
    return useApiService('users', { isAdmin: true })
}
```

## Extending a service

The advantage of specialized services is being able to add custom methods:

```javascript
import { useApiService } from 'vue-fastedgy/composables/api'

export function useTasksService() {
    const baseService = useApiService('tasks')

    return {
        ...baseService,

        // Custom method
        markCompleted: async (id) => {
            return baseService.update(id, {
                completed: true,
                completed_at: new Date().toISOString()
            })
        },

        // Method with business logic
        getActiveTasks: async () => {
            return baseService.list({
                filter: { completed: false },
                orderBy: ['-priority', 'created_at']
            })
        }
    }
}
