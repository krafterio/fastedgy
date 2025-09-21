# Database Connection

FastEdgy handles database connection completely automatically with a native lifespan. You don't need to configure or manage the connection manually.

## Automatic setup

FastEdgy uses [Edgy ORM](https://edgy.dymmond.com) and automatically sets up the database connection when your application starts.

### Environment configuration

Set your database URL in your environment file (`.env`):

```env
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
# or
DATABASE_URL=sqlite:///./database.db
```

### Application lifecycle management

FastEdgy automatically manages the database connection through a **native lifespan**. No configuration required:

```python
from fastedgy.app import FastEdgy

def app():
    # DB connection is managed automatically - no lifespan needed
    return FastEdgy(
        title="My App",
        description="My FastEdgy application",
    )
```

!!! note "Automatic connection"
    FastEdgy automatically starts and stops the database connection through its integrated native lifespan. You no longer need to manually manage `db.connect()` and `db.disconnect()`.

### Custom lifespan (optional)

If you need to add your own startup/shutdown logic, you can provide a custom lifespan that will be composed with the native lifespan:

```python
from contextlib import asynccontextmanager
from fastedgy.app import FastEdgy

@asynccontextmanager
async def custom_lifespan(app: FastEdgy):
    # Your custom startup logic
    print("Custom startup logic...")
    yield
    # Your custom shutdown logic
    print("Custom shutdown logic...")

def app():
    # FastEdgy composes your lifespan with its native lifespan
    return FastEdgy(
        title="My App",
        lifespan=custom_lifespan,  # Optional
    )
```

## Manual connection management (if needed)

In rare cases where you need manual control:

```python
from fastedgy.dependencies import Inject
from fastedgy.orm import Database

async def manual_connection(db: Database = Inject(Database)):
    await db.connect()
    try:
        # Your database operations here
        pass
    finally:
        await db.disconnect()
```

## Automatic connection pooling

FastEdgy automatically configures connection pooling:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

## Multiple database support

For advanced use cases with multiple databases, refer to the [Edgy ORM documentation](https://edgy.dymmond.com/tenancy/edgy).

## Summary

- **Zero configuration**: Connection handled automatically via native lifespan
- **Environment-based**: Configure via `DATABASE_URL`
- **Automatic lifecycle**: Opens on startup, closes on shutdown
- **Connection pooling**: Automatic with configurable settings
- **Built on Edgy**: Full Edgy ORM compatibility
- **No lifespan required**: Native lifespan manages everything

The database connection is ready to use as soon as your FastEdgy application starts!
