# API Routes Generator

**Automatic CRUD endpoints generation for Edgy models**

The API Routes Generator automatically creates complete REST API endpoints for your Edgy models with just a decorator. It generates all standard CRUD operations (Create, Read, Update, Delete, List) with advanced features like filtering, field selection, and pagination.

## Key Features

- **Automatic CRUD Generation**: Complete REST endpoints with a single decorator
- **Standard Actions**: List, Get, Create, Update, Delete, and Export endpoints
- **Field Selection**: Control response fields with HTTP headers ([Fields Selector](../fields-selector/overview.md))
- **Advanced Filtering**: Query filtering with multiple operators ([Query Builder](../query-builder/overview.md))
- **Pagination Support**: Built-in pagination for list endpoints
- **Ordering**: Sort results by any field
- **View Transformers**: Custom data transformation pipeline
- **Admin Routes**: Separate endpoints for admin operations
- **Full FastAPI Integration**: Native FastAPI router generation

## Why API Routes Generator vs Manual Routes?

### Manual FastAPI Routes Problems
- **Repetitive Code**: Every model needs the same CRUD boilerplate
- **Inconsistent APIs**: Different developers implement different patterns
- **Missing Features**: [Filtering](../query-builder/overview.md), pagination, [field selection](../fields-selector/overview.md) require manual implementation
- **Maintenance Overhead**: Changes to models require updating multiple endpoints

### API Routes Generator Advantages
- **Zero Boilerplate**: One decorator generates all endpoints
- **Consistent APIs**: All models follow the same REST patterns
- **Built-in Features**: [Filtering](../query-builder/overview.md), pagination, and [field selection](../fields-selector/overview.md) included
- **Type Safety**: Automatic Pydantic schema generation from Edgy models
- **Extensible**: Custom actions and transformers for specialized needs

## Quick Example

```python
from fastedgy.orm import Model, fields
from fastedgy.api_route_model import api_route_model

@api_route_model()
class User(Model):
    name = fields.CharField(max_length=100)
    email = fields.EmailField()
    age = fields.IntegerField()

    class Meta:
        tablename = "users"

# Automatically generates these endpoints:
# GET /users/          - List all users (with pagination, filtering, ordering)
# POST /users/         - Create a new user
# GET /users/{id}/     - Get a specific user
# PATCH /users/{id}/   - Update a user
# DELETE /users/{id}/  - Delete a user
# GET /users/export    - Export users data
```

## Generated Endpoints

For each registered model, the following endpoints are automatically created:

| Method | Endpoint | Action | Features |
|--------|----------|---------|----------|
| GET | `/models/` | List items | Pagination, [filtering](../query-builder/overview.md), ordering, [field selection](../fields-selector/overview.md) |
| POST | `/models/` | Create item | Validation, [field selection](../fields-selector/overview.md) |
| GET | `/models/{id}/` | Get item | [Field selection](../fields-selector/overview.md) |
| PATCH | `/models/{id}/` | Update item | Partial updates, [field selection](../fields-selector/overview.md) |
| DELETE | `/models/{id}/` | Delete item | Soft/hard delete |
| GET | `/models/export` | Export data | Multiple formats |

## Common Use Cases

- **CRUD APIs**: Quick REST API creation for data models
- **Admin Interfaces**: Separate admin endpoints with different permissions
- **Mobile Apps**: Consistent API endpoints with [field selection](../fields-selector/overview.md)
- **Data Export**: Built-in export functionality
- **Prototyping**: Rapid API development during development

## Get Started

Ready to generate your first API routes? Follow our quick start guide:

[Getting Started](getting-started.md){ .md-button .md-button--primary }
[User Guide](guide.md){ .md-button }
