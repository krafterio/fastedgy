# Routers

**Utility functions for Vue Router query management and redirects**

The Router utilities provide helper functions for managing route query parameters, handling redirects, and manipulating route data in Vue applications.

## Key Features

- **Query Management**: Add, merge, and restore route query parameters
- **Redirect Handling**: Manage redirect flows between routes
- **Parameter Encoding**: Safely encode/decode complex query values
- **Route Manipulation**: Replace and update route queries

## Available Functions

- `addQueries()`: Add query parameters to a route
- `addRedirect()`: Add redirect to route query parameters
- `getRedirect()`: Get redirect URL from route query
- `hasRedirect()`: Check if route has redirect parameter
- `mergeRouteQueryValues()`: Merge query values into route/URLSearchParams
- `replaceRouteQuery()`: Replace query values in current route
- `restoreRouteQuery()`: Restore and decode query parameter value
- `redirectIfExist()`: Redirect if redirect parameter exists

## Quick Example

```javascript
import {
  addQueries,
  addRedirect,
  getRedirect,
  mergeRouteQueryValues,
  replaceRouteQuery,
  restoreRouteQuery
} from 'vue-fastedgy'

// Add queries to a route
const routeWithQueries = addQueries(currentRoute, { name: 'users' }, {
  status: 'active',
  page: 1
})

// Add redirect parameter
const routeWithRedirect = addRedirect(currentRoute, { name: 'login' })

// Get redirect URL
const redirectUrl = getRedirect(currentRoute, { name: 'home' })

// Merge query values
mergeRouteQueryValues({
  filter: { status: 'active' },
  sort: 'name'
}, route, 'search')

// Restore complex query parameter
const filters = restoreRouteQuery('filters', currentRoute, 'search', {}, 'object')
```

## Common Use Cases

- **Login Redirects**: Save intended destination before login
- **Form State**: Persist filter/search state in URL
- **Navigation Flows**: Handle multi-step processes with redirects
- **URL Synchronization**: Keep complex UI state in sync with URL

## Get Started

Ready to use router utilities? Check out the practical guide:

[User Guide](guide.md){ .md-button .md-button--primary }
