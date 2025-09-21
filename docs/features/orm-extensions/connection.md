# Database Connection

FastEdgy handles database connection automatically. The connection is pre-configured and managed through the application lifespan, so you don't need to manage it manually.

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

FastEdgy automatically manages the database connection through the lifespan context:

```python
from contextlib import asynccontextmanager
from fastedgy.app import FastEdgy
from fastedgy.dependencies import Inject
from fastedgy.orm import Database

@asynccontextmanager
async def lifespan(app: FastEdgy):
    # Database connection opens automatically
    db = app.get_service(Database)
    await db.connect()
    try:
        yield
    finally:
        # Database connection closes automatically
        await db.disconnect()

def app():
    return FastEdgy(lifespan=lifespan)
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

- **Zero configuration**: Connection handled automatically
- **Environment-based**: Configure via `DATABASE_URL`
- **Lifespan managed**: Opens on startup, closes on shutdown
- **Connection pooling**: Automatic with configurable settings
- **Built on Edgy**: Full Edgy ORM compatibility

The database connection is ready to use as soon as your FastEdgy application starts!
