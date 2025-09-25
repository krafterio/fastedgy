# Bus

**Event communication system for Vue.js components**

The Bus provides a lightweight event system for communication between Vue components, services, and external systems. It enables loose coupling and reactive data flow throughout your application.

## Key Features

- **Global Events**: Publish and subscribe to events across your entire application
- **Custom Events**: Built on browser's native CustomEvent API
- **Async Support**: Wait for event handlers with `triggerAndWait()`
- **Memory Management**: Automatic cleanup and unsubscribe mechanisms
- **Vue Lifecycle Integration**: Automatic listener cleanup on component unmount

## Common Use Cases

- **Cross-component Communication**: Send data between unrelated components
- **Service Integration**: Bridge between Vue components and business logic services
- **Real-time Updates**: Handle WebSocket messages and server-sent events
- **User Interface Events**: Coordinate complex UI interactions

## Quick Example

```javascript
import { bus, useBus } from 'vue-fastedgy'

// Trigger an event
bus.trigger('user:updated', { id: 123, name: 'John Doe' })

// Trigger and wait for all handlers to complete
await bus.triggerAndWait('data:sync', { table: 'users' })

// In a Vue component - automatic cleanup
useBus(bus, 'user:updated', (event) => {
  console.log('User updated:', event.detail)
})
```

## Get Started

Ready to use the Bus in your application? Check out our [user guide](guide.md) for detailed examples and patterns.

[Get Started with Bus](guide.md){ .md-button .md-button--primary }
