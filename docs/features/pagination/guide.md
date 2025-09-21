# Pagination - Usage Guide

## Query Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `limit` | int | 50 | 1-1000 | Number of items per page |
| `offset` | int | 0 | ≥0 | Number of items to skip |

## Response Structure

```python
{
    "items": [/* array of items */],
    "total": 1250,      # Total items in dataset
    "limit": 50,        # Items per page (requested)
    "offset": 100,      # Items skipped
}
```

## Frontend Integration

### Calculate Page Info

```javascript
const response = await fetch('/api/products/?limit=25&offset=50')
const data = await response.json()

const pageInfo = {
    currentPage: Math.floor(data.offset / data.limit) + 1,  // 3
    totalPages: Math.ceil(data.total / data.limit),         // 50
    hasNext: data.offset + data.limit < data.total,         // true
    hasPrev: data.offset > 0                                // true
}
```

### Navigation Links

```javascript
const buildPageUrl = (page, limit = 25) => {
    const offset = (page - 1) * limit
    return `/api/products/?limit=${limit}&offset=${offset}`
}

// Next page
const nextUrl = buildPageUrl(pageInfo.currentPage + 1)

// Previous page
const prevUrl = buildPageUrl(pageInfo.currentPage - 1)
```

## Performance Considerations

- **Large Offsets**: Avoid very large offsets (>10000) for performance
- **Count Queries**: Total count requires a separate COUNT query

## Common Patterns

```bash
# Small pages for mobile
GET /api/products/?limit=10

# Table view with standard page size
GET /api/products/?limit=25

# Bulk operations
GET /api/products/?limit=1000

# Combined with search
GET /api/products/?limit=20&offset=40
X-Filter: ["name", "contains", "laptop"]
```

[Back to Overview](overview.md){ .md-button }
