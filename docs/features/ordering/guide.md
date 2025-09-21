# Ordering - Usage Guide

## Syntax Reference

| Format | Example | Description |
|--------|---------|-------------|
| `field` | `name` | Ascending by field (default) |
| `field:asc` | `name:asc` | Explicit ascending |
| `field:desc` | `price:desc` | Descending |
| `field1,field2` | `name,price:desc` | Multiple fields |
| `relation.field` | `user.name` | Nested relation field |

## Direction Options

- `asc` or omitted: Ascending order (A→Z, 1→9, oldest→newest)
- `desc`: Descending order (Z→A, 9→1, newest→oldest)

## Common Examples

### Basic Sorting

```bash
# Alphabetical by name
GET /api/products/?order_by=name

# Most expensive first
GET /api/products/?order_by=price:desc

# Newest first
GET /api/products/?order_by=created_at:desc

# Boolean fields (active items first)
GET /api/products/?order_by=is_active:desc
```

### Multiple Fields

```bash
# Category first, then price descending
GET /api/products/?order_by=category,price:desc

# Active first, then newest, then alphabetical
GET /api/products/?order_by=is_active:desc,created_at:desc,name
```

### Nested Relations

```bash
# Sort by user's full name
GET /api/orders/?order_by=user.name

# Sort by category name, then product price
GET /api/products/?order_by=category.name,price:desc

# Sort by user's company name
GET /api/orders/?order_by=user.profile.company.name

# Mixed local and relation fields
GET /api/orders/?order_by=status,user.name,created_at:desc
```

## Model Default Ordering

Configure default sort order in your model:

```python
from fastedgy.api_route_model.params import OrderByList
from fastedgy.orm import Model, fields

class Product(Model):
    name = fields.CharField(max_length=100)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    created_at = fields.DateTimeField(auto_now_add=True)

    class Meta:
        tablename = "products"
        # String format
        default_order_by: str = "name:asc"

        # Or typed list format
        default_order_by: OrderByList = [("name", "asc")]

        # Multiple fields
        default_order_by: OrderByList = [("category", "asc"), ("price", "desc")]
```

## Performance Tips

- **Index Fields**: Add database indexes for frequently sorted fields
- **Relation Sorting**: Uses SQL JOINs, ensure foreign keys are indexed
- **Limit Results**: Combine with pagination for better performance

[Back to Overview](overview.md){ .md-button }
