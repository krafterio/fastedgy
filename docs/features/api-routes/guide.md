# API Routes Generator - User Guide

This guide shows you how to use the API Routes Generator effectively with practical examples and common patterns.

## Customizing Generated Routes

You can control which endpoints are generated and customize their behavior:

### Selective Endpoint Generation

```python
from fastedgy.api_route_model import api_route_model

# Enable only list and get endpoints
@api_route_model(list=True, get=True, create=False, patch=False, delete=False)
class ReadOnlyProduct(Model):
    name = fields.CharField(max_length=200)
    price = fields.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        tablename = "readonly_products"

# Custom endpoint configuration
@api_route_model(
    list=True,
    get=True,
    create={"status_code": 201, "summary": "Create a new product"},
    patch={"summary": "Update product details"},
    delete=False  # Disable delete endpoint
)
class Product(Model):
    name = fields.CharField(max_length=200)
    description = fields.TextField()
    price = fields.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        tablename = "products"
```

## Built-in Features

Generated endpoints automatically integrate with FastEdgy's advanced features:

- **[Pagination](../pagination/overview.md)** - Standard limit/offset pagination with metadata
- **[Ordering](../ordering/overview.md)** - Sort by any field including nested relations
- **[Query Builder](../query-builder/overview.md)** - Advanced filtering with X-Filter header
- **[Fields Selector](../fields-selector/overview.md)** - Control response fields with X-Fields header

```bash
# Example combining all features
GET /api/products/?limit=25&order_by=category.name,price:desc
X-Filter: ["&", [["is_active", "=", true], ["price", ">=", 100]]]
X-Fields: name,price,category.name,description
```

## Working with Relationships

Generated endpoints support Edgy model relationships:

```bash
# Create with foreign key reference
POST /api/products/
{"name": "Smartphone", "category": 1, "price": "599.99"}

# Filter by related fields
GET /api/products/
X-Filter: ["category.name", "=", "Electronics"]

GET /api/products/
X-Filter: ["category", "=", 1]
```

## Data Export

Every model gets automatic export functionality supporting CSV, XLSX, and ODS formats:

```bash
# Export with all features support
GET /api/products/export?format=csv&limit=1000
X-Filter: ["is_active", "=", true]
X-Fields: name,price,category.name
```

## Error Handling

Generated endpoints provide consistent error responses:

- **400 Bad Request**: Validation errors with field details
- **404 Not Found**: Item not found
- **403 Forbidden**: Insufficient permissions
- **422 Unprocessable Entity**: Invalid request data

## Admin Routes

Create separate admin endpoints with different permissions:

```python
from fastedgy.api_route_model import admin_api_route_model

@admin_api_route_model()  # Separate from regular routes
class AdminUser(Model):
    username = fields.CharField(max_length=150)
    is_staff = fields.BooleanField(default=False)

# Register on separate admin router
admin_router = APIRouter(prefix="/admin/api", dependencies=[Depends(admin_required)])
register_admin_api_route_models(admin_router)
```

## Performance Optimization

Generated endpoints include automatic optimizations:

- **Query Optimization**: Automatic `select_related()` for filtered/selected relations
- **Memory Management**: [Pagination](../pagination/overview.md) prevents large dataset memory issues
- **Data Transfer**: [Field selection](../fields-selector/overview.md) reduces response size

## Next Steps

Ready for more advanced customization? Check out:

- **[Advanced Usage](advanced.md)** - Custom actions and route customization
- **[View Transformers](../view-transformers/overview.md)** - Data transformation hooks

[Advanced Usage Guide](advanced.md){ .md-button .md-button--primary }
