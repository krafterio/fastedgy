---
hide:
  - navigation
---

# Getting Started

## Prerequisites

- Python 3.13+
- UV (Python Package Manager recommended, see the [installation doc](https://docs.astral.sh/uv/getting-started/installation))
- PostgreSQL 15.0+

## Installation

### Using UV (Recommended)

```bash
uv add git+ssh://git@github.com/krafterio/fastedgy.git
```

### Using pip

```bash
pip install git+ssh://git@github.com/krafterio/fastedgy.git
```

## Project Structure

FastEdgy follows a structured approach. Here's a minimal project layout:

```
my_project/
├── main.py          # App factory
├── models.py        # Database models
├── api/
│   └── users.py     # API routes
├── services/
│   └── email.py     # Business logic
└── settings.py      # Configuration
```

## Quick Start

### 1. Create your models

**`models.py`:**
```python
from fastedgy.models import Model
from fastedgy.orm import fields

class User(Model):
    name = fields.CharField(max_length=100)
    email = fields.EmailField()

    class Meta:
        tablename = "users"
```

### 2. Create your services

**`services/email.py`:**
```python
class EmailService:
    async def send_welcome(self, email: str):
        print(f"Sending welcome email to {email}")
        # Your email logic here
```

### 3. Create your API routes

**`api/users.py`:**
```python
from fastapi import APIRouter
from fastedgy.dependencies import Inject
from fastedgy.queued_tasks import QueuedTasks

from models import User
from services.email import EmailService

router = APIRouter()

@router.post("/users/")
async def create_user(
    user_data: dict,
    email_service: EmailService = Inject(EmailService),
    tasks: QueuedTasks = Inject(QueuedTasks)
):
    user = User(**user_data)
    await user.save()

    # Queue background task
    await tasks.add_task(email_service.send_welcome, user.email)

    return user
```

### 4. Create your app factory

**`main.py`:**
```python
from fastapi import APIRouter

from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings, init_settings
from fastedgy.api_route_model.router import register_api_route_models
from fastedgy.api_route_model.standard_actions import register_standard_api_route_model_actions

from api import users
import models  # Import models to register them

class AppSettings(BaseSettings):
    title: str = "My FastEdgy App"
    debug: bool = True

def app():
    settings = init_settings(AppSettings)

    # FastEdgy handles DB connection and lifespan automatically
    app = FastEdgy(
        title=settings.title,
        description="My awesome FastEdgy application",
        version="1.0.0",
    )

    # Setup API routes
    api_router = APIRouter(prefix="/api")
    api_router.include_router(users.router)

    # Generate automatic CRUD routes for all models
    register_standard_api_route_model_actions()
    register_api_route_models(api_router)

    app.include_router(api_router)

    return app
```

!!! note "Automatic lifespan"
    FastEdgy automatically handles database connection and service cleanup with a native lifespan. The `lifespan` parameter is no required.

### Custom lifespan (optional)

If you need to add your own startup/shutdown logic, you can still provide a custom lifespan:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def custom_lifespan(application: FastEdgy):
    # Your startup logic
    print("Application starting...")
    yield
    # Your shutdown logic
    print("Application shutting down...")

app = FastEdgy(
    title=settings.title,
    lifespan=custom_lifespan,  # Optional
)
```

### 5. Run your application

```bash
fastedgy serve
```

Your API is now available at `http://localhost:8000` with automatic OpenAPI docs at `/docs`!

## Next Steps

- **[Explore Features](features/index.md)** - Discover all FastEdgy capabilities
- **[Container Service](features/container-service/overview.md)** - Learn dependency injection
- **[Queued Tasks](features/queued-tasks/overview.md)** - Handle background processing
