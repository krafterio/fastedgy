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

## Records the request may not read

A join reaches a record whatever that record's own global filters and access guards say. Before the answer leaves, the records the relations reach are asked to their model's own query, once per model for the whole page:

- **To-one relation**: a record the request may not read keeps its key alone, `"category": {"id": 5}`
- **Many-to-many relation**: a record the request may not read is left out of the list
- **Reverse relation**: read through the related model's own query, already narrowed

A model whose only filter is the workspace scope is never asked: every member of the workspace reads its records. A model only an access guard narrows is answered by the guard, without a query. Exports follow the same rule.

## Error handling

- **Invalid fields**: Silently ignored
- **Missing relations**: Returns null
- **Malformed syntax**: Falls back to all fields

[Back to Overview](overview.md){ .md-button }
