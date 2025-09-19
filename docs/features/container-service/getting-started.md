# Getting Started with Container Service

Get up and running with Container Service in 5 minutes. This guide covers the essentials you need to start using dependency injection in your FastAPI application.

## Prerequisites

- FastAPI application with FastEdgy
- Basic understanding of Python classes and FastAPI endpoints

## Step 1: Your First Service

Let's create a simple email service:

```python
# services/email.py
class EmailService:
    def __init__(self, smtp_host: str = "localhost"):
        self.smtp_host = smtp_host

    def send_email(self, to: str, subject: str, body: str):
        print(f"Sending email via {self.smtp_host} to {to}: {subject}")
        return {"sent": True, "to": to}
```

## Step 2: Use It in Your API

No registration needed - just inject it directly:

```python
# main.py
from fastapi import FastAPI
from fastedgy.dependencies import Inject
from services.email import EmailService

app = FastAPI()

@app.post("/send-email")
async def send_email(
    recipient: str,
    subject: str,
    body: str,
    email_service: EmailService = Inject(EmailService)  # Magic happens here!
):
    result = email_service.send_email(recipient, subject, body)
    return result
```

**That's it!** The `EmailService` is automatically created with default parameters when first requested.

## Step 3: Custom Configuration (Optional)

Need specific configuration? Register your service explicitly:

```python
# main.py
from fastedgy.dependencies import register_service

# Register with custom configuration
email_service = EmailService("smtp.company.com")
register_service(email_service)

# Now Inject(EmailService) returns your configured instance
```

## Step 4: Services with Dependencies

Container Service automatically resolves dependency chains:

```python
# services/notification.py
class DatabaseService:
    def __init__(self, connection_string: str = "sqlite:///app.db"):
        self.connection_string = connection_string

    def get_user_email(self, user_id: str):
        return f"user{user_id}@example.com"

class NotificationService:
    def __init__(self, email: EmailService, db: DatabaseService):
        self.email = email
        self.db = db

    def notify_user(self, user_id: str, message: str):
        user_email = self.db.get_user_email(user_id)
        return self.email.send_email(user_email, "Notification", message)
```

Use it directly - no manual wiring needed:

```python
@app.post("/notify/{user_id}")
async def notify_user(
    user_id: str,
    message: str,
    notifications: NotificationService = Inject(NotificationService)
):
    # NotificationService automatically gets EmailService and DatabaseService
    result = notifications.notify_user(user_id, message)
    return result
```

## What Just Happened?

When you use `Inject(NotificationService)`, the Container Service:

1. **Analyzes** the constructor: sees it needs `EmailService` and `DatabaseService`
2. **Resolves** `EmailService`: creates it with default parameters (or uses registered instance)
3. **Resolves** `DatabaseService`: creates it with default parameters
4. **Creates** `NotificationService` with both resolved dependencies
5. **Caches** all instances as singletons for future use

## Key Concepts

### Automatic Resolution
Services with simple constructors (default parameters or dependencies) are created automatically on first use.

### Explicit Registration
Use `register_service()` when you need:
- Custom configuration (database URLs, API keys, etc.)
- Complex initialization logic
- Startup validation

### Singleton Behavior
Services are created once and reused across all requests, perfect for database connections, caches, and configuration.

## Common Patterns

### Pattern 1: Configuration Service
```python
class AppConfig:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
        self.api_key = os.getenv("API_KEY", "dev-key")

# Auto-resolved - no registration needed
config: AppConfig = Inject(AppConfig)
```

### Pattern 2: Database Service
```python
class DatabaseService:
    def __init__(self, config: AppConfig):  # Depends on AppConfig
        self.connection_string = config.database_url
        # Connection logic here

# Auto-resolved with AppConfig dependency
db: DatabaseService = Inject(DatabaseService)
```

### Pattern 3: Explicit Registration
```python
# For services needing specific setup
redis_cache = CacheService("redis://production-cache:6379")
register_service(redis_cache)

# Now available everywhere
cache: CacheService = Inject(CacheService)
```

## Next Steps

You now know the basics! For more advanced usage:

- **[User Guide →](guide.md)** - Complete patterns and best practices
- **[Advanced Usage →](advanced.md)** - Complex scenarios and testing
- **[Technical Details →](technical.md)** - How it works under the hood

## Quick Reference

```python
# Import essentials
from fastedgy.dependencies import Inject, register_service, get_service

# Auto-resolution (most common)
service: MyService = Inject(MyService)

# Explicit registration
register_service(MyService("custom config"))

# Direct access (outside FastAPI context)
service = get_service(MyService)
```

Ready for more? **[Continue to User Guide →](guide.md)**
