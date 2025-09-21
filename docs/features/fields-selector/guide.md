# Fields Selector - Usage guide

## Basic syntax

```bash
# Comma-separated field list
GET /api/products/
X-Fields: name,price,description,is_active
```

## Special operators

| Operator | Description | Example |
|----------|-------------|---------|
| `+` | Include all fields | `+` |
| `field.nested` | Access nested relation | `category.name` |

## Selection patterns

### Simple fields
```bash
GET /api/users/
X-Fields: username,email,created_at
```

### Nested relations
```bash
GET /api/products/
X-Fields: name,price,category.name,category.parent.name
```

### All fields
```bash
GET /api/products/
X-Fields: +
```

### Mixed selection
```bash
GET /api/products/
X-Fields: +,category.name,category.description
```

## Query optimization

Fields Selector automatically optimizes database queries:

- **Relations**: Adds `select_related()` for dot notation fields
- **Joins**: Prevents N+1 query problems
- **Columns**: Reduces selected columns when possible

## Response format

```json
{
  "id": 1,
  "name": "Laptop",
  "price": 999.99,
  "category": {
    "id": 5,
    "name": "Electronics"
  }
}
```

## Error handling

- **Invalid fields**: Silently ignored
- **Missing relations**: Returns null
- **Malformed syntax**: Falls back to all fields

[Back to Overview](overview.md){ .md-button }
