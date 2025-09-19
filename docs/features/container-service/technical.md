# Container Service Technical Details

Deep dive into the Container Service architecture, implementation details, and comparisons with other dependency injection systems.

## Why Build on FastAPI Instead of External DI Libraries?

Popular Python dependency injection libraries like **Dependency Injector** and **Injector** offer powerful features, but FastEdgy's Container Service provides several advantages specifically for FastAPI applications.

### vs Dependency Injector

**Dependency Injector** is feature-rich but introduces additional complexity and learning curve:

**FastEdgy Advantages:**
- **Native FastAPI Integration**: No conflicts between FastAPI's `Depends()` and external DI systems
- **Zero Additional Dependencies**: Built on FastAPI's existing infrastructure
- **Simplified Learning Curve**: Same patterns and syntax as FastAPI
- **Type Safety**: Leverages FastAPI's existing type resolution without additional configuration
- **Automatic Resolution**: Works out-of-the-box without complex container configuration files

**Dependency Injector Comparison:**
```python
# Dependency Injector approach - requires configuration
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    database = providers.Singleton(
        DatabaseService,
        connection_string=config.database_url
    )

    email_service = providers.Factory(
        EmailService,
        smtp_host=config.smtp_host
    )

# FastEdgy approach - zero configuration
class DatabaseService:
    def __init__(self, config: AppConfig):  # Auto-resolved
        self.connection_string = config.database_url

# Just use it - no container setup needed
db: DatabaseService = Inject(DatabaseService)
```

### vs Injector (Google Guice Style)

**Injector** provides clean dependency injection but requires a different mental model:

**FastEdgy Advantages:**
- **Consistent API**: Uses familiar FastAPI patterns rather than decorators like `@inject`
- **Request Context Compatibility**: Seamlessly handles both application-level and request-scoped dependencies
- **No Learning Overhead**: Developers already familiar with FastAPI can use it immediately
- **Unified Ecosystem**: Everything works together - CLI, API endpoints, background tasks

**Injector Comparison:**
```python
# Injector approach - different patterns
from injector import inject, Injector

class UserService:
    @inject
    def __init__(self, db: DatabaseService, email: EmailService):
        self.db = db
        self.email = email

injector = Injector()
user_service = injector.get(UserService)

# FastEdgy approach - FastAPI-native
class UserService:
    def __init__(self, db: DatabaseService, email: EmailService):
        self.db = db
        self.email = email

# Works in FastAPI endpoints naturally
@router.post("/users")
async def create_user(service: UserService = Inject(UserService)):
    return service.create_user(data)
```

### The FastEdgy Philosophy

By building on FastAPI's native dependency system, FastEdgy ensures:

- **One System**: No conflicts or confusion between different DI approaches
- **Full Compatibility**: Works with all FastAPI features, middleware, and extensions
- **Progressive Enhancement**: Adds convenience without changing fundamental FastAPI patterns
- **Maintenance**: No external dependencies to maintain or version conflicts to resolve

## Architecture Overview

The Container Service is built around several core components that work together to provide dependency injection capabilities. At its heart is the `ContainerService` class which maintains a service registry, handles lazy loading, manages dependency resolution, and integrates with FastAPI's existing dependency system.

### Key Concepts

1. **Service Registry**: A centralized store that maintains all registered services and their factory functions
2. **Lazy Loading**: Services are instantiated only when first requested, not during registration
3. **Dependency Cache**: Previously resolved dependencies are cached to improve performance on subsequent requests
4. **FastAPI Integration**: Seamless compatibility with FastAPI's native dependency injection system

### Registration Process

The registration process intelligently adapts to different input types and handles each appropriately. When registering a direct instance, it's stored immediately in the service registry. For factory functions, the callable is stored and will be invoked on first access. For class registration, a wrapper function is created that automatically resolves the class's constructor dependencies using FastAPI's dependency resolution system, then instantiates the class with those resolved dependencies.

### Dependency Resolution Process

The automatic dependency resolution follows these steps:

1. **Inspect Class**: Analyze class constructor parameters using Python's type hints
2. **Resolve Dependencies**: Use FastAPI's dependency system to resolve each parameter recursively
3. **Create Instance**: Instantiate the class with resolved dependencies
4. **Cache Result**: Store the instance as a singleton for future access

### Integration with FastAPI

The `Inject()` function creates FastAPI-compatible dependencies that integrate seamlessly with the existing dependency system. When you use `Inject(MyService)` in an endpoint, it creates a standard FastAPI dependency that retrieves the container service and then gets the requested service from it.

What makes this integration particularly powerful is that dependencies are shared between both systems rather than duplicated. Application-level services (like database connections, configuration, or caches) registered in the Container Service are the same instances accessed through FastAPI's native `Depends()` system. This ensures consistency, avoids resource duplication, and maintains proper singleton behavior across your entire application.

## Implementation Details

### Type System Integration

The Container Service leverages Python's type system for automatic dependency resolution:

```python
# The Container Service analyzes this constructor
class NotificationService:
    def __init__(self, email: EmailService, cache: CacheService, config: AppConfig):
        #           ^^^^^^^^^^^^    ^^^^^^^^^^^^    ^^^^^^^^^^
        #           |               |               |
        #           These type hints drive automatic resolution
```

When resolving `NotificationService`, the system:

1. Extracts parameter types: `EmailService`, `CacheService`, `AppConfig`
2. Recursively resolves each dependency
3. Handles nested dependencies (e.g., if `EmailService` needs `AppConfig`)
4. Creates instances in the correct order
5. Caches all instances for reuse

### Singleton Management

Services follow singleton behavior by default:

- **First Access**: Service is created and stored in the registry
- **Subsequent Access**: Same instance is returned from cache
- **Thread Safety**: Service creation is thread-safe for concurrent requests
- **Memory Management**: Services live for the application lifetime

### Error Handling

The Container Service provides clear error messages for common issues:

```python
# Missing dependency
try:
    service = get_service(UnconfiguredService)
except LookupError as e:
    # Error: No instance registered for <class 'UnconfiguredService'>

# Circular dependency detection
try:
    service = get_service(CircularService)
except Exception as e:
    # Error: Circular dependency detected in ServiceA -> ServiceB -> ServiceA
```

## Performance Characteristics

### Service Creation Overhead

- **Registration**: O(1) - services stored in dictionary
- **First Resolution**: O(n) where n = dependency depth
- **Subsequent Access**: O(1) - cached instances returned
- **Memory**: Minimal overhead, services created only when needed

### Comparison with FastAPI Native

```python
# FastAPI native - function called on every request
def get_database():
    return DatabaseService("postgresql://...")  # Created each time

@router.get("/users")
async def get_users(db: DatabaseService = Depends(get_database)):
    pass  # db is recreated for each request

# Container Service - singleton created once
@router.get("/users")
async def get_users(db: DatabaseService = Inject(DatabaseService)):
    pass  # db is reused across all requests
```

**Performance Benefits:**
- **Reduced Memory**: No duplicate service instances
- **Faster Response Times**: No service recreation per request
- **Connection Pooling**: Database connections properly shared
- **Stateful Services**: Can maintain caches and state efficiently

## Advanced Internals

### Dependency Graph Resolution

The Container Service builds a dependency graph and resolves it in topological order:

```
AppConfig (leaf)
├── DatabaseService(config)
├── EmailService(config)
└── NotificationService(email, database)
```

Resolution order: `AppConfig` → `DatabaseService` + `EmailService` → `NotificationService`

### Lazy Evaluation Strategy

Services use lazy evaluation for optimal performance:

1. **Registration Phase**: Only metadata is stored
2. **First Access**: Dependency graph is built and resolved
3. **Instance Creation**: Services created in dependency order
4. **Caching**: Instances cached for future access

### Memory Management

The Container Service is designed for long-running applications:

- **Service Instances**: Held as strong references (singletons)
- **Dependency Cache**: Cleared on application shutdown
- **Factory Functions**: Garbage collected after first execution
- **Type Metadata**: Minimal memory footprint

## Testing Integration

### Service Isolation

The Container Service supports test isolation through service override:

```python
# Production code
register_service(ProductionEmailService())

# Test code
register_service(MockEmailService(), EmailService, force=True)
# All subsequent Inject(EmailService) returns mock

# Test cleanup
unregister_service(EmailService)
```

### Dependency Mocking

Complex services can be partially mocked:

```python
# Mock only the database, keep other services real
class TestDatabaseService:
    def __init__(self):
        self.data = {}  # In-memory storage for tests

    def query(self, sql: str):
        # Test-specific implementation
        pass

register_service(TestDatabaseService(), DatabaseService, force=True)

# UserService automatically gets the test database
user_service = get_service(UserService)  # Uses TestDatabaseService
```

## Debugging and Introspection

### Service Registry Inspection

```python
from fastedgy.dependencies import get_container_service

container = get_container_service()

# Check if service is registered
if container.has(DatabaseService):
    print("DatabaseService is registered")

# List all registered services (for debugging)
for key in container._map:  # Internal access for debugging only
    print(f"Registered: {key}")
```

### Dependency Tracing

Enable debug logging to trace dependency resolution:

```python
import logging

# Enable detailed logging
logging.getLogger('fastedgy.dependencies').setLevel(logging.DEBUG)

# Now see resolution steps
service = get_service(ComplexService)
# DEBUG: Resolving ComplexService
# DEBUG: Resolving dependency EmailService
# DEBUG: Resolving dependency DatabaseService
# DEBUG: Creating ComplexService instance
# DEBUG: Caching ComplexService
```

## Best Practices for Large Applications

### Service Organization

```python
# services/
#   core/
#     database.py      # DatabaseService
#     config.py        # AppConfig
#     logging.py       # LoggerService
#   business/
#     users.py         # UserService
#     orders.py        # OrderService
#     payments.py      # PaymentService
#   external/
#     email.py         # EmailService
#     notifications.py # NotificationService
```

### Service Registration Strategy

```python
# config/services.py
def register_core_services():
    """Register foundational services first."""
    register_service(AppConfig())
    register_service(LoggerService)
    register_service(DatabaseService)

def register_business_services():
    """Register business logic services."""
    register_service(UserService)
    register_service(OrderService)
    register_service(PaymentService)

def register_external_services():
    """Register external integrations."""
    register_service(create_email_service, EmailService)
    register_service(create_notification_service, NotificationService)

# app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register in dependency order
    register_core_services()
    register_business_services()
    register_external_services()
    yield
```

### Monitoring and Health Checks

```python
class ServiceHealthCheck:
    """Monitor service health and dependencies."""

    def __init__(self):
        self.container = get_container_service()

    def check_service_health(self):
        health_status = {}

        critical_services = [
            DatabaseService,
            CacheService,
            EmailService
        ]

        for service_type in critical_services:
            try:
                service = get_service(service_type)
                if hasattr(service, 'ping'):
                    await service.ping()
                health_status[service_type.__name__] = "healthy"
            except Exception as e:
                health_status[service_type.__name__] = f"unhealthy: {e}"

        return health_status
```

## Migration from Other DI Systems

### From Manual Dependencies

```python
# Before: Manual dependency management
class UserService:
    def __init__(self):
        self.db = DatabaseService(DATABASE_URL)
        self.email = EmailService(SMTP_HOST)
        self.logger = LoggerService(LOG_LEVEL)

# After: Automatic dependency injection
class UserService:
    def __init__(self,
                 db: DatabaseService,
                 email: EmailService,
                 logger: LoggerService):
        self.db = db
        self.email = email
        self.logger = logger
```

### From FastAPI Depends()

```python
# Before: Verbose FastAPI dependencies
def get_database():
    return DatabaseService(DATABASE_URL)

def get_user_service(db: DatabaseService = Depends(get_database)):
    return UserService(db)

@router.get("/users")
async def get_users(service: UserService = Depends(get_user_service)):
    pass

# After: Clean Container Service
@router.get("/users")
async def get_users(service: UserService = Inject(UserService)):
    pass  # UserService and DatabaseService auto-resolved
```

## Performance Tuning

### Service Creation Optimization

```python
# Expensive service initialization
class MLModelService:
    def __init__(self, config: AppConfig):
        # Load large ML model - expensive!
        self.model = load_model(config.model_path)

# Optimize with factory and caching
@lru_cache(maxsize=1)
def create_ml_model(config: AppConfig = Inject(AppConfig)):
    return MLModelService(config)

register_service(create_ml_model, MLModelService)
```

### Memory Usage Monitoring

```python
import sys
import gc

def monitor_service_memory():
    """Monitor memory usage of registered services."""
    container = get_container_service()

    total_size = 0
    service_sizes = {}

    for key, instance in container._map.items():
        if not callable(instance):  # Skip factories
            size = sys.getsizeof(instance)
            service_sizes[key] = size
            total_size += size

    print(f"Total service memory: {total_size} bytes")
    for service, size in service_sizes.items():
        print(f"  {service}: {size} bytes")
```

## Conclusion

The Container Service provides a powerful, FastAPI-native approach to dependency injection that maintains simplicity while offering advanced features. By building on FastAPI's existing infrastructure rather than introducing external dependencies, it ensures seamless integration and optimal performance for FastAPI applications.

## Quick Reference

### Core Functions
```python
# Service registration
register_service(instance)                    # Auto-key from type
register_service(instance, CustomKey)         # Custom key
register_service(factory_fn, ServiceType)     # Factory registration

# Service access
service = get_service(ServiceType)            # Direct access
service: ServiceType = Inject(ServiceType)    # FastAPI injection

# Service management
unregister_service(ServiceType)              # Remove service
has_service(ServiceType)                     # Check existence
```

### Advanced Features
```python
# Custom tokens
TOKEN = Token[ServiceType]("name")
register_service(instance, TOKEN)
service = Inject(TOKEN)

# Service override (testing)
register_service(mock, RealService, force=True)

# Container access (debugging)
container = get_container_service()
container.clear_cache()
```
