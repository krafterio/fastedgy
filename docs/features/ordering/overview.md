# Ordering

Sort API results by any field including nested relationships using simple query parameters.

## Key Features

- **Simple Syntax**: `field:direction` format with comma separation
- **Nested Relations**: Sort by related model fields (e.g., `user.name`, `category.slug`)
- **Multiple Fields**: Combine multiple sort criteria
- **Direction Control**: Ascending (`asc`) and descending (`desc`) support
- **Default Ordering**: Configure default sort order per model
- **Field Validation**: Only valid model fields are accepted

## Basic Syntax

```bash
# Single field ascending (default)
GET /api/products/?order_by=name

# Single field descending
GET /api/products/?order_by=price:desc

# Multiple fields
GET /api/products/?order_by=category:asc,price:desc,name:asc
```

## Nested Relations Support

Sort by fields from related models:

```bash
# Sort by related user name
GET /api/orders/?order_by=user.name

# Sort by category name, then product price
GET /api/products/?order_by=category.name,price:desc

# Deep nested relations
GET /api/orders/?order_by=user.profile.company.name
```

## Works With All Features

```bash
# Ordered filtered results
GET /api/products/?order_by=price:desc
X-Filter: ["category", "=", "electronics"]

# Ordered pagination
GET /api/products/?order_by=created_at:desc&limit=25&offset=50
```

[Usage Guide](guide.md){ .md-button .md-button--primary }
