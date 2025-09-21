# API Routes Generator - Getting Started

Learn how to automatically generate CRUD endpoints for your Edgy models in just a few steps.

## Prerequisites

- FastEdgy application set up
- Edgy models defined
- Basic understanding of FastAPI routers

## Basic Setup

### 1. Register Standard Actions

First, register the standard CRUD actions in your application setup:

```python
# main.py
from fastedgy.api_route_model.standard_actions import register_standard_api_route_model_actions

def app():
    # Register standard actions (list, get, create, patch, delete, export)
    register_standard_api_route_model_actions()

    # ... rest of your app setup
```

### 2. Mark Your Models

Add the `@api_route_model()` decorator to your Edgy models:

```python
# models.py
from fastedgy.orm import Model, fields
from fastedgy.api_route_model import api_route_model

@api_route_model()
class Product(Model):
    name = fields.CharField(max_length=200)
    description = fields.TextField()
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    is_active = fields.BooleanField(default=True)

    class Meta:
        tablename = "products"

@api_route_model()
class Category(Model):
    name = fields.CharField(max_length=100)
    slug = fields.SlugField()

    class Meta:
        tablename = "categories"
```

### 3. Register Generated Routes

Include the generated routes in your FastAPI application:

```python
# main.py
from fastapi import APIRouter
from fastedgy.api_route_model.router import register_api_route_models

def app():
    app = FastEdgy()

    # Register standard actions
    register_standard_api_route_model_actions()

    # Create API router
    api_router = APIRouter(prefix="/api")

    # Register all generated routes
    register_api_route_models(api_router)

    # Include the router in your app
    app.include_router(api_router)

    return app
```

## Test Your Endpoints

Once set up, your models automatically have full CRUD endpoints:

### List Products
```bash
GET /api/products/

# With pagination
GET /api/products/?limit=10&offset=20

# With filtering
GET /api/products/
X-Filter: ["price", ">=", 100]

# With ordering
GET /api/products/?order_by=name,-price
```

!!! tip "Advanced Features"
    See **[Query Builder](../query-builder/overview.md)** for complete X-Filter syntax and operators.

### Create Product
```bash
POST /api/products/
Content-Type: application/json

{
  "name": "Laptop",
  "description": "High-performance laptop",
  "price": "999.99",
  "is_active": true
}
```

### Get Product
```bash
GET /api/products/1/

# With field selection
GET /api/products/1/
X-Fields: name,price
```

!!! tip "Field Selection"
    See **[Fields Selector](../fields-selector/overview.md)** for nested field selection and advanced options.

### Update Product
```bash
PATCH /api/products/1/
Content-Type: application/json

{
  "price": "899.99",
  "is_active": false
}
```

### Delete Product
```bash
DELETE /api/products/1/
```

## What's Generated

The `@api_route_model()` decorator automatically creates:

- **Pydantic schemas** for request/response validation
- **FastAPI routes** with proper HTTP methods
- **OpenAPI documentation** with model schemas
- **Error handling** with proper HTTP status codes
- **[Pagination](../pagination/overview.md)** for list endpoints
- **[Ordering](../ordering/overview.md)** with nested relations support
- **[Filtering capabilities](../query-builder/overview.md)** based on model fields
- **[Field selection](../fields-selector/overview.md)** for optimized responses

## Next Steps

Your API Routes Generator is now set up! Learn more advanced features:

- **[User Guide](guide.md)** - [Pagination](../pagination/overview.md), [ordering](../ordering/overview.md), [filtering](../query-builder/overview.md), [field selection](../fields-selector/overview.md), and customization
- **[Advanced Usage](advanced.md)** - Custom actions and [view transformers](../view-transformers/overview.md)

[Continue to User Guide](guide.md){ .md-button .md-button--primary }
