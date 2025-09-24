# API Service

**Generic service for CRUD operations with FastEdgy APIs**

The API Service provides a standardized abstraction layer for all CRUD (Create, Read, Update, Delete) operations with FastEdgy APIs. It automatically handles URL construction, query parameters, specialized headers, and FastEdgy conventions.

## Key features

- **Complete CRUD**: List, Get, Create, Update, Delete, Export
- **FastEdgy conventions**: Automatic support for X-Fields headers, order_by, pagination
- **Admin mode**: Automatic switching between public and admin APIs
- **Extensible**: Facilitates creation of specialized services
- **Standardized types**: Consistent interface for all resources

## Recommended usage

Create specialized services rather than using the generic directly:

```javascript
import { useApiService } from 'vue-fastedgy/composables/api'

export function useTasksService() {
    return useApiService('tasks')
}

export function useUsersService() {
    return useApiService('users', { isAdmin: true })
}
```

## Quick example

```javascript
const tasksService = useTasksService()

// Simple CRUD operations
await tasksService.list({ page: 1, size: 20 })
await tasksService.create({ title: 'New task' })
await tasksService.update(123, { completed: true })
await tasksService.delete(123)
```

## Get started

Ready to use the API Service? Check out our guide:

[User Guide](guide.md){ .md-button .md-button--primary }
