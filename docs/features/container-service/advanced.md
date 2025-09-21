# Advanced Container Service Usage

Advanced patterns for complex applications including testing, custom tokens, lifecycle management, and sophisticated dependency scenarios.

## Custom Token Keys

Use tokens when you need multiple implementations of the same service type or string-based service keys.

### Multiple Database Connections

```python
from fastedgy.dependencies import Token, register_service, Inject

# Define custom tokens
PRIMARY_DB = Token[DatabaseService]("primary_db")
ANALYTICS_DB = Token[DatabaseService]("analytics_db")
CACHE_DB = Token[DatabaseService]("cache_db")

# Register different database instances
register_service(
    DatabaseService("postgresql://primary-server/app"),
    PRIMARY_DB
)
register_service(
    DatabaseService("postgresql://analytics-server/warehouse"),
    ANALYTICS_DB
)
register_service(
    DatabaseService("redis://cache-server:6379"),
    CACHE_DB
)

# Use specific databases in endpoints
@router.get("/analytics")
async def get_analytics(
    primary_db: DatabaseService = Inject(PRIMARY_DB),
    analytics_db: DatabaseService = Inject(ANALYTICS_DB)
):
    users = primary_db.query("SELECT * FROM users")
    analytics_db.query("INSERT INTO user_analytics ...")
    return {"user_count": len(users)}
```

### Environment-Based Services

```python
# Define environment-specific tokens
DEV_EMAIL = Token[EmailService]("dev_email")
PROD_EMAIL = Token[EmailService]("prod_email")

def setup_email_services():
    if os.getenv("ENVIRONMENT") == "production":
        register_service(SMTPEmailService("smtp.mailgun.org"), PROD_EMAIL)
        register_service(SMTPEmailService("smtp.mailgun.org"), EmailService)  # Default
    else:
        register_service(ConsoleEmailService(), DEV_EMAIL)
        register_service(ConsoleEmailService(), EmailService)  # Default

@router.post("/notify")
async def notify_user(
    email_service: EmailService = Inject(EmailService)  # Gets environment-appropriate service
):
    return email_service.send_email("user@example.com", "Hello", "World")
```

## Advanced Factory Patterns

### Factory Functions with Dependencies

Create factories that inject other services during construction:

```python
def create_payment_processor(
    config: AppConfig = Inject(AppConfig),
    logger: LoggerService = Inject(LoggerService),
    db: DatabaseService = Inject(DatabaseService)
) -> PaymentProcessor:
    """Factory that configures payment processor based on environment."""

    if config.environment == "production":
        processor = StripePaymentProcessor(
            api_key=config.stripe_api_key,
            logger=logger
        )
    else:
        processor = MockPaymentProcessor(logger=logger)

    # Common initialization
    processor.setup_webhooks()
    processor.register_event_handlers(db)

    return processor

# Register the factory
register_service(create_payment_processor, PaymentProcessor)

# Use in endpoints
@router.post("/payments")
async def process_payment(
    amount: float,
    processor: PaymentProcessor = Inject(PaymentProcessor)
):
    return processor.charge(amount)
```

### Conditional Service Creation

```python
def create_notification_service(
    config: AppConfig = Inject(AppConfig)
) -> NotificationService:
    """Create notification service with multiple channels based on config."""

    channels = []

    if config.email_enabled:
        channels.append(EmailNotificationChannel(config.smtp_host))

    if config.sms_enabled:
        channels.append(SMSNotificationChannel(config.twilio_key))

    if config.slack_enabled:
        channels.append(SlackNotificationChannel(config.slack_webhook))

    return NotificationService(channels)

register_service(create_notification_service, NotificationService)
```

## Service Lifecycle Management

### Startup and Shutdown Hooks

Manage service initialization and cleanup using FastAPI's lifespan system:

```python
from contextlib import asynccontextmanager
from fastedgy import FastEdgy

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize services

    # Register services with complex initialization
    database = DatabaseService(DATABASE_URL)
    await database.connect()
    register_service(database)

    # Initialize background services
    task_processor = TaskProcessor()
    await task_processor.start()
    register_service(task_processor)

    # Register dependent services
    register_service(UserService)  # Will use registered DatabaseService
    register_service(EmailService)

    try:
        yield  # Application runs here
    finally:
        # Shutdown: cleanup services
        db = get_service(DatabaseService)
        await db.disconnect()

        processor = get_service(TaskProcessor)
        await processor.shutdown()

app = FastEdgy(lifespan=lifespan)
```

### Health Checks and Monitoring

```python
class HealthCheckService:
    def __init__(self,
                 db: DatabaseService,
                 cache: CacheService,
                 external_api: ExternalAPIService):
        self.db = db
        self.cache = cache
        self.external_api = external_api

    async def check_health(self):
        checks = {}

        # Database check
        try:
            await self.db.ping()
            checks["database"] = {"status": "healthy"}
        except Exception as e:
            checks["database"] = {"status": "unhealthy", "error": str(e)}

        # Cache check
        try:
            await self.cache.ping()
            checks["cache"] = {"status": "healthy"}
        except Exception as e:
            checks["cache"] = {"status": "unhealthy", "error": str(e)}

        # External API check
        try:
            await self.external_api.ping()
            checks["external_api"] = {"status": "healthy"}
        except Exception as e:
            checks["external_api"] = {"status": "unhealthy", "error": str(e)}

        return checks

# Auto-resolved with all dependencies
@router.get("/health")
async def health_check(health: HealthCheckService = Inject(HealthCheckService)):
    return await health.check_health()
```

## Testing and Mocking

### Service Override for Testing

Replace real services with mocks during testing:

```python
import pytest
from unittest.mock import Mock
from fastedgy.dependencies import register_service, unregister_service

class MockEmailService:
    def __init__(self):
        self.sent_emails = []

    def send_email(self, to: str, subject: str, body: str):
        email = {"to": to, "subject": subject, "body": body}
        self.sent_emails.append(email)
        return {"sent": True, "id": f"mock-{len(self.sent_emails)}"}

class MockDatabaseService:
    def __init__(self):
        self.data = {}
        self.queries = []

    def query(self, sql: str):
        self.queries.append(sql)
        return {"mock": "result"}

    def create_user(self, user_data: dict):
        user_id = len(self.data) + 1
        user = {"id": user_id, **user_data}
        self.data[user_id] = user
        return user

@pytest.fixture
def mock_services():
    """Replace services with mocks for testing."""

    # Create mocks
    mock_email = MockEmailService()
    mock_db = MockDatabaseService()

    # Override services
    register_service(mock_email, EmailService, force=True)
    register_service(mock_db, DatabaseService, force=True)

    yield {
        "email": mock_email,
        "database": mock_db
    }

    # Cleanup
    unregister_service(EmailService)
    unregister_service(DatabaseService)

def test_user_registration(mock_services):
    """Test user registration with mocked services."""

    # Test the endpoint
    response = client.post("/register", json={
        "email": "test@example.com",
        "name": "Test User"
    })

    assert response.status_code == 200

    # Verify email was sent
    assert len(mock_services["email"].sent_emails) == 1
    assert mock_services["email"].sent_emails[0]["to"] == "test@example.com"

    # Verify user was created
    assert len(mock_services["database"].data) == 1
    assert mock_services["database"].data[1]["email"] == "test@example.com"
```

### Integration Testing with Real Services

```python
@pytest.fixture(scope="session")
def test_database():
    """Create a test database for integration tests."""

    # Setup test database
    test_db_url = "postgresql://test:test@localhost/test_db"
    test_db = DatabaseService(test_db_url)

    # Initialize schema
    test_db.create_tables()

    # Override the service
    register_service(test_db, DatabaseService, force=True)

    yield test_db

    # Cleanup
    test_db.drop_tables()
    unregister_service(DatabaseService)

def test_user_service_integration(test_database):
    """Test UserService with real database."""

    user_service = get_service(UserService)  # Uses test database

    # Test user creation
    user = user_service.create_user({
        "email": "integration@test.com",
        "name": "Integration Test"
    })

    assert user["id"] is not None
    assert user["email"] == "integration@test.com"

    # Test user retrieval
    retrieved_user = user_service.get_user(user["id"])
    assert retrieved_user["email"] == "integration@test.com"
```

### Testing Factory Services

```python
def test_payment_processor_factory():
    """Test that payment processor factory creates correct implementation."""

    # Test production configuration
    prod_config = AppConfig()
    prod_config.environment = "production"
    prod_config.stripe_api_key = "test_key"

    register_service(prod_config, AppConfig, force=True)

    processor = get_service(PaymentProcessor)
    assert isinstance(processor, StripePaymentProcessor)
    assert processor.api_key == "test_key"

    # Test development configuration
    dev_config = AppConfig()
    dev_config.environment = "development"

    register_service(dev_config, AppConfig, force=True)

    # Force recreation of payment processor
    unregister_service(PaymentProcessor)

    processor = get_service(PaymentProcessor)
    assert isinstance(processor, MockPaymentProcessor)
```

## Complex Dependency Scenarios

### Circular Dependencies (Advanced Resolution)

Handle circular dependencies with lazy loading:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.order_service import OrderService

class UserService:
    def __init__(self, db: DatabaseService):
        self.db = db
        self._order_service = None

    @property
    def order_service(self) -> 'OrderService':
        if self._order_service is None:
            from fastedgy.dependencies import get_service
            from services.order_service import OrderService
            self._order_service = get_service(OrderService)
        return self._order_service

    def get_user_orders(self, user_id: str):
        return self.order_service.get_orders_for_user(user_id)

class OrderService:
    def __init__(self, db: DatabaseService, user_service: UserService):
        self.db = db
        self.user_service = user_service

    def create_order(self, order_data: dict):
        user = self.user_service.get_user(order_data["user_id"])
        # Create order logic...
```

### Dynamic Service Resolution

```python
class ServiceRegistry:
    """Dynamic service locator for plugin-like architecture."""

    def __init__(self):
        self.handlers = {}

    def register_handler(self, event_type: str, handler_class: type):
        self.handlers[event_type] = handler_class

    def get_handler(self, event_type: str):
        handler_class = self.handlers.get(event_type)
        if not handler_class:
            raise ValueError(f"No handler registered for {event_type}")

        # Use Container Service to resolve handler dependencies
        from fastedgy.dependencies import get_service
        return get_service(handler_class)

# Register dynamic service
register_service(ServiceRegistry())

# Register event handlers
def setup_event_handlers():
    registry = get_service(ServiceRegistry)

    registry.register_handler("user.created", UserCreatedHandler)
    registry.register_handler("order.completed", OrderCompletedHandler)
    registry.register_handler("payment.failed", PaymentFailedHandler)

class EventProcessor:
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry

    async def process_event(self, event_type: str, event_data: dict):
        handler = self.registry.get_handler(event_type)  # Auto-resolved with dependencies
        return await handler.handle(event_data)
```

## Performance Optimization

### Lazy Loading Services

```python
class ExpensiveService:
    """Service with expensive initialization."""

    def __init__(self, config: AppConfig):
        print("Initializing expensive service...")
        # Expensive initialization here
        self.expensive_resource = self._load_expensive_resource()

    def _load_expensive_resource(self):
        # Simulate expensive operation
        time.sleep(2)
        return "expensive resource"

# Don't register directly - use factory for lazy loading
def create_expensive_service(config: AppConfig = Inject(AppConfig)):
    return ExpensiveService(config)

register_service(create_expensive_service, ExpensiveService)

# Service is only created when first accessed
@router.get("/expensive-operation")
async def expensive_operation(
    service: ExpensiveService = Inject(ExpensiveService)  # Created here if first time
):
    return service.expensive_resource
```

### Caching and Memoization

```python
from functools import lru_cache

class CacheService:
    def __init__(self):
        self._cache = {}

    @lru_cache(maxsize=128)
    def get_expensive_data(self, key: str):
        # Expensive computation
        return f"expensive_result_for_{key}"

    def clear_cache(self):
        self.get_expensive_data.cache_clear()

# Singleton ensures cache is shared across requests
cached_service: CacheService = Inject(CacheService)
```

## Error Handling and Debugging

### Service Registration Validation

```python
from contextlib import asynccontextmanager
from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service

def validate_services():
    """Validate that all required services are properly registered."""

    required_services = [
        DatabaseService,
        EmailService,
        CacheService,
        PaymentProcessor
    ]

    missing_services = []

    for service_class in required_services:
        try:
            get_service(service_class)
        except LookupError:
            missing_services.append(service_class.__name__)

    if missing_services:
        raise RuntimeError(f"Missing required services: {missing_services}")

# Optional custom lifespan for service validation
@asynccontextmanager
async def lifespan(app: FastEdgy):
    setup_services()
    validate_services()  # Ensure all services are available
    yield

# FastEdgy handles DB and core services automatically
app = FastEdgy(
    title="My App",
    lifespan=lifespan,  # Optional - only for custom validation logic
)
```

### Custom Error Handling

```python
class ServiceError(Exception):
    """Base exception for service-related errors."""
    pass

class ServiceConfigurationError(ServiceError):
    """Raised when a service is misconfigured."""
    pass

def create_database_service(config: AppConfig = Inject(AppConfig)):
    """Factory with error handling."""

    if not config.database_url:
        raise ServiceConfigurationError(
            "DATABASE_URL is required but not configured"
        )

    try:
        return DatabaseService(config.database_url)
    except Exception as e:
        raise ServiceConfigurationError(f"Failed to create database service: {e}")

register_service(create_database_service, DatabaseService)
```

## Next Steps

This covers the advanced usage patterns. For implementation details and architectural information:

**[Technical Details →](technical.md)**

Or return to simpler guides:

- **[Getting Started ←](getting-started.md)**
- **[User Guide ←](guide.md)**

## Advanced Quick Reference

```python
# Custom tokens
PRIMARY_DB = Token[DatabaseService]("primary")
register_service(db_instance, PRIMARY_DB)
db: DatabaseService = Inject(PRIMARY_DB)

# Factories with dependencies
def create_service(dep: DepService = Inject(DepService)):
    return MyService(dep, custom_config)
register_service(create_service, MyService)

# Testing overrides
register_service(mock_service, RealService, force=True)
# ... run tests ...
unregister_service(RealService)

# Service validation
try:
    service = get_service(MyService)
except LookupError:
    print("Service not registered")
```
