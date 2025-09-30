# Edgy ORM Extensions - Overview

FastEdgy extends [Edgy ORM](https://edgy.dymmond.com) with additional features and provides seamless integration with FastAPI applications.

## Key features

- **Built on Edgy ORM**: Full compatibility with Edgy ORM features and syntax
- **FastAPI integration**: Automatic dependency injection and service integration
- **Type safety**: Full Python type hints support
- **Async/await**: Native asynchronous database operations
- **Automatic migrations**: Database schema management with Alembic
- **Query builders**: Intuitive and powerful query API

## What FastEdgy adds to Edgy ORM

FastEdgy extends Edgy ORM with:

- **Base models**: Pre-configured model foundation with FastEdgy services
- **Dependency injection**: Automatic service injection in models
- **Context management**: Workspace and user context integration
- **API route generation**: Automatic CRUD endpoints from models
- **Enhanced field types**: Additional specialized fields (Vector, HTML, Phone, Geospatial Coordinates)

## Quick example

```python
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields
from fastedgy.api_route_model import api_route_model
from fastedgy.i18n import _t

@api_route_model()
class Product(BaseModel):
    class Meta:
        tablename = "products"
        label = _t('Product')
        label_plural = _t('Products')

    name = fields.CharField(max_length=255, label=_t('Product Name'))
    price = fields.DecimalField(max_digits=10, decimal_places=2, label=_t('Price'))
    is_active = fields.BooleanField(default=True, label=_t('Is Active'))

# Usage
product = Product(name="Laptop", price=999.99)
await product.save()

products = await Product.query.filter(is_active=True).all()
```

## Architecture

- **Connection**: Automatic database connection management
- **Models**: Powerful model definitions with relationships
- **Fields**: Rich field types for all data needs
- **Queries**: Type-safe query building
- **Migrations**: Schema evolution with Alembic

FastEdgy's ORM provides all of Edgy ORM's power with additional FastAPI-specific features for building modern web applications.
