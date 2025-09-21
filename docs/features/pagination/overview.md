# Pagination

Built-in pagination for all list endpoints using standard `limit` and `offset` parameters.

## Key Features

- **Automatic Integration**: Available on all generated list endpoints
- **Configurable Limits**: Default 50 items, max 1000 per request
- **Total Count**: Includes total items count for UI pagination
- **Standard Response**: Consistent pagination response format
- **Zero Configuration**: Works out of the box with any model

## Response Format

```json
{
  "items": [...],
  "total": 1250,
  "limit": 50,
  "offset": 100
}
```

## Basic Usage

```bash
# First page (default)
GET /api/products/

# Custom page size
GET /api/products/?limit=25

# Navigate pages
GET /api/products/?limit=25&offset=50

# Large datasets (up to 1000 items)
GET /api/products/?limit=1000
```

## Works With All Features

Pagination combines seamlessly with filtering, ordering, and field selection:

```bash
# Paginated filtered results
GET /api/products/?limit=10&offset=20
X-Filter: ["category", "=", "electronics"]

# Paginated with ordering
GET /api/products/?limit=10&order_by=name:asc

# Paginated with field selection
GET /api/products/?limit=10
X-Fields: name,price,category.name
```

[Usage Guide](guide.md){ .md-button .md-button--primary }
