# Multi Tenant - Usage guide

## Using WorkspaceableMixin

### Add workspace support to models
The simplest way to make a model workspace-aware is to use the `WorkspaceableMixin`:

```python
from fastedgy.orm import Model, fields
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.models.base import BaseModel

class Product(BaseModel, WorkspaceableMixin):
    name = fields.CharField(max_length=100)
    price = fields.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        tablename = "products"
```

### Automatic workspace assignment
Models with `WorkspaceableMixin` automatically get assigned to the current workspace:

- **Workspace field**: Foreign key relationship added automatically
- **Context-aware saves**: Records saved to the current workspace context
- **Filtered queries**: Default queries only return workspace-specific records

### Workspace managers
FastEdgy provides specialized managers for workspace-aware queries:

- **`query`**: Returns only records from the current workspace
- **`global_query`**: Returns records from all workspaces (admin use)

## Basic workspace operations

### Create workspace-scoped records
```python
# Within workspace context, records are automatically scoped
product = await Product.query.create(
    name="Laptop",
    price=999.99
)
```

### Query workspace-specific data
```python
# Only returns products from the current workspace
products = await Product.query.all()

# Access all products across workspaces (admin)
all_products = await Product.global_query.all()
```

## Advanced multi-tenancy

For advanced multi-tenancy patterns including schema-based and database-based tenancy, refer to the comprehensive [Edgy ORM Tenancy documentation](https://edgy.dymmond.com/tenancy/edgy).

Key Edgy ORM features available in FastEdgy:

- **`using(schema=...)`**: Query specific database schemas
- **`using_with_db(...)`**: Query different databases
- **`with_tenant(...)`**: Set global tenant context
- **Schema management**: Automatic schema creation and management

## Configuration

Workspace multi-tenancy works with FastEdgy's context system. The workspace context is typically set by:

- **Authentication middleware**: Set workspace based on user credentials
- **API headers**: Extract workspace from request headers
- **URL routing**: Determine workspace from URL patterns

[Back to Overview](overview.md){ .md-button }
