# Container Service

A centralized dependency injection system that makes FastAPI development simpler by automatically managing service dependencies.

## The Problem

FastAPI's native `Depends()` system requires verbose boilerplate and manual wiring for application-level services:

```python
# FastAPI native approach - lots of boilerplate
def get_database():
    return DatabaseService("postgresql://...")

def get_email_service(db: DatabaseService = Depends(get_database)):
    return EmailService(db)

@app.post("/users")
async def create_user(
    user_data: dict,
    db: DatabaseService = Depends(get_database),
    email: EmailService = Depends(get_email_service)
):
    # Every endpoint needs explicit dependencies
```

## The Solution

Container Service automatically resolves dependencies with zero boilerplate:

```python
# Container Service - clean and simple
from fastedgy.dependencies import Inject

@app.post("/users")
async def create_user(
    user_data: dict,
    email: EmailService = Inject(EmailService)  # Auto-resolved!
):
    # EmailService gets DatabaseService automatically
```

## Key Benefits

- **Zero boilerplate** - No provider functions needed
- **Automatic resolution** - Dependencies resolved recursively
- **Application singletons** - Services persist across requests
- **Unified access** - Same services in API, CLI, and background tasks
- **Full FastAPI compatibility** - Built on native dependency system

## Quick Start

New to Container Service? Start here:

[Get Started →](getting-started.md){ .md-button .md-button--primary }

## Documentation Structure

<div class="grid cards" markdown>

-   :material-rocket-launch: **Getting Started**

    ---

    5-minute guide to your first Container Service setup

    [:material-arrow-right: Start here](getting-started.md)

-   :material-book-open-variant: **User Guide**

    ---

    Complete guide for everyday usage patterns

    [:material-arrow-right: Learn more](guide.md)

-   :material-cog: **Advanced Usage**

    ---

    Complex patterns, testing, and lifecycle management

    [:material-arrow-right: Advanced topics](advanced.md)

-   :material-atom: **Technical Details**

    ---

    Architecture, comparisons, and implementation details

    [:material-arrow-right: Technical info](technical.md)

</div>

## When to Use Container Service

**Perfect for:**
- Database connections and configurations
- Email services, caches, external APIs
- Services shared across endpoints
- Application-level singletons

**Not needed for:**
- Simple request-scoped data
- FastAPI's built-in features (authentication, etc.)
- One-off utilities

Ready to get started? **[→ Getting Started Guide](getting-started.md)**
