# Database Migration - Usage Guide

This guide shows how to use FastEdgy's enhanced Alembic integration for database migrations.

## Setup

Create the database:

```bash
fastedgy db createdb
```

Initialize the migration repository with FastEdgy's template:

```bash
fastedgy db init
```

This creates a migration directory with FastEdgy-optimized configuration.

## Creating migrations

Generate a new migration based on model changes:

```bash
fastedgy db makemigrations -m "Add user model"
```

FastEdgy automatically detects:

- New models and fields
- Required PostgreSQL extensions (vector, enums)
- Database views
- Field type changes

## Model with enum field

```python
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.i18n import _t
from enum import Enum

class UserStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"

class User(BaseModel):
    class Meta:
        tablename = "users"

    name = fields.CharField(max_length=100, label=_t('Name'))
    status = fields.ChoiceField(choices=UserStatus, default=UserStatus.active, label=_t('Status'))
```

The generated migration will automatically:

- Create the enum type
- Handle enum column creation
- Add necessary imports

## Model with vector field

```python
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.i18n import _t

class Document(BaseModel):
    class Meta:
        tablename = "documents"

    title = fields.CharField(max_length=255, label=_t('Title'))
    embedding = fields.VectorField(dimensions=1536, label=_t('AI Embedding'))
```

FastEdgy automatically:

- Enables the vector extension in PostgreSQL
- Creates vector columns with proper dimensions
- Handles vector-specific operations

## Running migrations

Apply migrations to the database:

```bash
fastedgy db migrate
```

Rollback migrations:

```bash
fastedgy db downgrade -1
```

## Migration files

FastEdgy generates enhanced migration files with:

- Automatic imports for FastEdgy-specific types
- Multi-database support functions
- Proper handling of nullable fields
- Vector extension management
- Enum type operations

## Best practices

- **Review generated migrations**: Always check auto-generated migrations before applying
- **Test rollbacks**: Ensure downgrade functions work correctly
- **Use descriptive messages**: Clear migration messages help track changes
- **Keep migrations small**: Split large changes into multiple migrations

[Back to Overview](overview.md){ .md-button }
