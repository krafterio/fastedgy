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

### ForeignKey relationships

Generated endpoints support foreign key references:

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

### ManyToMany & OneToMany relationships

FastEdgy provides two modes for managing collections of related records.

#### Simple mode

For small sets or complete replacements, use a simple list of IDs:

```bash
# Create with related items
POST /api/products/
{
  "name": "Laptop",
  "tags": [1, 2, 3]
}

# Replace all relations
PATCH /api/products/42
{
  "tags": [4, 5, 6]
}
```

The simple mode automatically executes a `set` operation that replaces all existing relations.

#### Advanced mode

For large collections or partial updates, use granular operations to avoid performance issues:

!!! info "Performance optimization"
    When a product has 1000 linked tags and you want to add just one more, simple mode would require sending 1001 IDs and the server would unlink 1000 relations then re-link 1001. Advanced mode lets you send just `["link", 1001]` for optimal performance.

**Available operations:**

| Operation | Description | Example Value |
|-----------|-------------|---------------|
| `link` | Add relation to existing record | `["link", 42]` |
| `unlink` | Remove relation (keep record) | `["unlink", 23]` |
| `create` | Create new record and link it | `["create", {"name": "New"}]` |
| `update` | Update record and ensure link | `["update", {"id": 10, "name": "Updated"}]` |
| `delete` | Delete record and remove relation | `["delete", 15]` |
| `set` | Replace all relations | `["set", [1, 2, 3]]` |
| `clear` | Remove all relations | `["clear"]` |

**When to use each operation:**

- **`link`** - Add one item to a large existing collection without touching others
- **`unlink`** - Remove one item from a large collection
- **`set`** - Reset the entire collection (same as simple mode)
- **`clear`** - Revoke all access or empty the collection
- **`create`** - Create and link in a single operation
- **`update`** - Modify a linked record and ensure the link exists
- **`delete`** - Permanently remove a linked record

**Examples:**

```bash
# Add one item to existing large collection
PATCH /api/products/42
{
  "tags": [["link", 1001]]
}

# Multiple targeted modifications
PATCH /api/products/42
{
  "tags": [
    ["link", 50],
    ["unlink", 23],
    ["update", {"id": 10, "name": "Updated Name"}]
  ]
}

# Create and link in one request
POST /api/products/
{
  "name": "Gaming Laptop",
  "tags": [
    ["link", 1],
    ["create", {"name": "Limited Edition"}]
  ]
}

# Complete reset (equivalent to simple mode)
PATCH /api/products/42
{
  "tags": [["set", [1, 2, 3]]]
}

# Clear all relations
PATCH /api/products/42
{
  "tags": [["clear"]]
}
```

**Operation order:**

Operations are executed sequentially in the order provided:

```bash
PATCH /api/products/42
{
  "tags": [
    ["clear"],              # 1. Remove all existing tags
    ["link", 1],            # 2. Add tag 1
    ["link", 2],            # 3. Add tag 2
    ["create", {"name": "New Tag"}]  # 4. Create and add new tag
  ]
}
```

**Error responses:**

```json
// 400 Bad Request - Record not found
{
  "detail": "Record with id=999 not found in Tag"
}

// 400 Bad Request - Invalid operation format
{
  "detail": "Invalid operation format: ['link']. Expected [action, value] format."
}
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
