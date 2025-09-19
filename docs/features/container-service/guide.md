# Container Service User Guide

Complete guide to using Container Service effectively in your FastAPI applications. This covers the patterns you'll use in everyday development.

## Service Registration Patterns

### Pattern 1: Auto-Resolution (Recommended)

For services with default constructors or simple dependencies:

```python
class ConfigService:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost/myapp")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"

class DatabaseService:
    def __init__(self, config: ConfigService):  # Auto-resolved dependency
        self.connection_string = config.database_url

# No registration needed - use directly
@router.get("/health")
async def health_check(db: DatabaseService = Inject(DatabaseService)):
    return {"status": "healthy", "database": db.connection_string}
```

**When to use:** Services with environment variables, default configurations, or simple dependencies.

### Pattern 2: Explicit Instance Registration

For services requiring specific configuration:

```python
# Register configured instances during app startup
email_service = EmailService(
    smtp_host="smtp.company.com",
    username="noreply@company.com",
    password=os.getenv("EMAIL_PASSWORD")
)
register_service(email_service)

# Use anywhere in your application
@router.post("/welcome")
async def send_welcome_email(
    user_email: str,
    email: EmailService = Inject(EmailService)
):
    return email.send_email(user_email, "Welcome!", "Thanks for joining!")
```

**When to use:** Database connections, external APIs, services with secrets/credentials.

### Pattern 3: Factory Functions

For expensive or conditional service creation:

```python
def create_cache_service():
    if os.getenv("ENVIRONMENT") == "production":
        return RedisCache("redis://production-cache:6379")
    else:
        return InMemoryCache()

# Register the factory
register_service(create_cache_service, CacheService)

# Service is created on first access
@router.get("/cached-data")
async def get_cached_data(cache: CacheService = Inject(CacheService)):
    return cache.get("key")  # Factory called here if first time
```

**When to use:** Environment-specific services, expensive initialization, conditional logic.

## Working with FastAPI

### Standard Endpoint Usage

Container Service integrates seamlessly with FastAPI's dependency system:

```python
@router.post("/orders")
async def create_order(
    order_data: dict,
    db: DatabaseService = Inject(DatabaseService),
    email: EmailService = Inject(EmailService),
    notifications: NotificationService = Inject(NotificationService)
):
    # All services automatically resolved and injected
    order = db.create_order(order_data)
    email.send_confirmation(order.user_email)
    notifications.notify_user(order.user_id, "Order created!")
    return order
```

### Mixing with FastAPI Depends()

You can mix Container Service with regular FastAPI dependencies:

```python
from fastapi.security import HTTPBearer

security = HTTPBearer()

@router.get("/protected")
async def protected_endpoint(
    token: str = Depends(security),  # Standard FastAPI dependency
    user_service: UserService = Inject(UserService)  # Container Service
):
    user = user_service.get_user_from_token(token.credentials)
    return {"user": user.username}
```

### Request vs Application Scope

Understanding when to use each:

```python
# Application-scoped (Container Service) - singletons
class DatabaseService:  # One instance for entire app
    def __init__(self):
        self.connection_pool = create_pool()

class ConfigService:  # Configuration doesn't change per request
    def __init__(self):
        self.settings = load_settings()

# Request-scoped (FastAPI Depends) - created per request
async def get_current_user(token: str = Depends(oauth2_scheme)):
    return decode_token(token)  # Different user per request

def get_request_id():
    return str(uuid.uuid4())  # Unique per request

@router.get("/user-data")
async def get_user_data(
    current_user: User = Depends(get_current_user),  # Request-scoped
    request_id: str = Depends(get_request_id),       # Request-scoped
    db: DatabaseService = Inject(DatabaseService),   # App-scoped
    config: ConfigService = Inject(ConfigService)    # App-scoped
):
    # Mix both patterns as needed
```

## Complex Dependency Chains

### Shared Dependencies

When multiple services need the same dependency:

```python
class ConfigService:
    def __init__(self):
        self.email_host = os.getenv("EMAIL_HOST")
        self.cache_url = os.getenv("CACHE_URL")

class EmailService:
    def __init__(self, config: ConfigService):
        self.host = config.email_host

class CacheService:
    def __init__(self, config: ConfigService):  # Same ConfigService instance
        self.url = config.cache_url

class NotificationService:
    def __init__(self, email: EmailService, cache: CacheService):
        self.email = email
        self.cache = cache

# Auto-resolution creates this tree:
# ConfigService (singleton)
# ├── EmailService(config)
# ├── CacheService(config)
# └── NotificationService(email, cache)
```

### Deep Dependency Trees

Container Service handles complex dependency graphs automatically:

```python
class LoggerService:
    def __init__(self, config: ConfigService):
        self.level = config.log_level

class DatabaseService:
    def __init__(self, config: ConfigService, logger: LoggerService):
        self.connection = create_connection(config.database_url)
        self.logger = logger

class UserService:
    def __init__(self, db: DatabaseService, cache: CacheService):
        self.db = db
        self.cache = cache

class OrderService:
    def __init__(self,
                 user_service: UserService,
                 email: EmailService,
                 logger: LoggerService):
        self.users = user_service
        self.email = email
        self.logger = logger

# Just inject the top-level service - everything else resolves automatically
@router.post("/orders")
async def create_order(
    order_data: dict,
    orders: OrderService = Inject(OrderService)  # Entire tree resolved!
):
    return orders.create_order(order_data)
```

## Cross-Context Usage

### Using Services in CLI Commands

Services work identically in CLI commands:

```python
from fastedgy.cli import command
from fastedgy.dependencies import get_service

@command()
def send_bulk_emails():
    """CLI command to send bulk emails."""
    email_service = get_service(EmailService)  # Same instance as API
    user_service = get_service(UserService)

    users = user_service.get_all_users()
    for user in users:
        email_service.send_email(user.email, "Newsletter", "Content...")
        print(f"Sent to {user.email}")
```

### Background Tasks

Same services available in background tasks:

```python
from fastapi import BackgroundTasks

def send_welcome_email_task(user_email: str):
    # Access services directly
    email_service = get_service(EmailService)
    template_service = get_service(TemplateService)

    template = template_service.get_template("welcome")
    email_service.send_email(user_email, "Welcome!", template)

@router.post("/register")
async def register_user(
    user_data: dict,
    background_tasks: BackgroundTasks,
    user_service: UserService = Inject(UserService)
):
    user = user_service.create_user(user_data)

    # Schedule background task
    background_tasks.add_task(send_welcome_email_task, user.email)

    return {"user_id": user.id}
```

## Environment-Specific Configuration

### Development vs Production Services

```python
def setup_services():
    """Configure services based on environment during startup."""
    env = os.getenv("ENVIRONMENT", "development")

    if env == "production":
        # Production services
        register_service(
            DatabaseService("postgresql://prod-db:5432/app"),
            DatabaseService
        )
        register_service(
            CacheService("redis://prod-cache:6379"),
            CacheService
        )
        register_service(
            EmailService(smtp_host="smtp.mailgun.org"),
            EmailService
        )
    else:
        # Development services
        register_service(
            DatabaseService("sqlite:///dev.db"),
            DatabaseService
        )
        register_service(InMemoryCache(), CacheService)
        register_service(ConsoleEmailService(), EmailService)

# Call during app startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_services()
    yield

app = FastAPI(lifespan=lifespan)
```

### Configuration Classes

```python
class DatabaseConfig:
    def __init__(self):
        self.url = os.getenv("DATABASE_URL", "sqlite:///app.db")
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
        self.echo = os.getenv("DB_ECHO", "false").lower() == "true"

class EmailConfig:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.username = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")

# Use configuration classes in services
class DatabaseService:
    def __init__(self, config: DatabaseConfig):  # Auto-injected
        self.engine = create_engine(
            config.url,
            pool_size=config.pool_size,
            echo=config.echo
        )
```

## Error Handling and Debugging

### Common Issues

**Service Not Found Error:**
```python
# Error: No instance registered for <class 'MyService'>

# Solution 1: Ensure service has default constructor or dependencies are registered
class MyService:
    def __init__(self, config: ConfigService = None):  # Default parameter
        self.config = config or ConfigService()

# Solution 2: Register explicitly
register_service(MyService("custom config"))
```

**Circular Dependencies:**
```python
# Problem: ServiceA needs ServiceB, ServiceB needs ServiceA
class ServiceA:
    def __init__(self, service_b: ServiceB):  # Circular!
        self.service_b = service_b

class ServiceB:
    def __init__(self, service_a: ServiceA):  # Circular!
        self.service_a = service_a

# Solution: Use factory pattern to break the cycle
def create_service_a(service_b: ServiceB = Inject(ServiceB)):
    return ServiceA(service_b)

register_service(ServiceB())  # Register first
register_service(create_service_a, ServiceA)  # Register factory
```

### Debug Mode

Enable logging to see what's happening:

```python
import logging

# Enable debug logging
logging.getLogger('fastedgy.dependencies').setLevel(logging.DEBUG)

# Now you'll see service creation and resolution steps
```

## Best Practices

### 1. Keep Services Focused
```python
# Good: Single responsibility
class EmailService:
    def send_email(self, to: str, subject: str, body: str):
        pass

class UserService:
    def create_user(self, user_data: dict):
        pass

# Avoid: Swiss Army knife services
class MegaService:
    def send_email(self, ...): pass
    def create_user(self, ...): pass
    def process_payment(self, ...): pass  # Too much!
```

### 2. Use Type Hints
```python
# Good: Clear type hints help auto-resolution
class NotificationService:
    def __init__(self, email: EmailService, logger: LoggerService):
        self.email = email
        self.logger = logger

# Avoid: No type hints make resolution impossible
class NotificationService:
    def __init__(self, email, logger):  # Can't auto-resolve
        self.email = email
        self.logger = logger
```

### 3. Explicit Registration for Complex Services
```python
# Good: Register complex services explicitly
database_service = DatabaseService(
    connection_string=DATABASE_URL,
    pool_size=20,
    echo=DEBUG_MODE
)
register_service(database_service)

# Avoid: Complex constructors without defaults
class DatabaseService:
    def __init__(self, connection_string, pool_size, echo):  # No defaults!
        pass
```

## Performance Considerations

### Singleton Benefits
- Services created once and reused
- Database connections pooled efficiently
- Configuration loaded once at startup
- Memory efficient for stateless services

### When to Avoid Singletons
- Services holding request-specific data
- Services that need to be reset between operations
- Testing scenarios requiring fresh instances

## Next Steps

- **[Advanced Usage →](advanced.md)** - Testing, tokens, and complex patterns
- **[Technical Details →](technical.md)** - Architecture and comparisons
- **[Getting Started ←](getting-started.md)** - Back to basics

## Quick Reference Card

```python
# Most common patterns
from fastedgy.dependencies import Inject, register_service, get_service

# 1. Auto-resolution (simplest)
service: MyService = Inject(MyService)

# 2. Explicit registration (custom config)
register_service(MyService("config"))
service: MyService = Inject(MyService)

# 3. Factory registration (conditional)
register_service(create_my_service, MyService)
service: MyService = Inject(MyService)

# 4. Direct access (outside FastAPI)
service = get_service(MyService)
```
