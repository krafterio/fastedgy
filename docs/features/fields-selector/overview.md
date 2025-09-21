# Fields Selector

Control which fields are included in API responses using the `X-Fields` header. Reduces bandwidth and improves performance by returning only requested data.

## Key features

- **Bandwidth reduction**: Only return requested fields
- **Dot notation**: Access nested relationships (`category.name`)
- **Query optimization**: Automatically adds `select_related()` for relations
- **Always includes ID**: Primary key always returned for consistency

## Use cases

- **Mobile APIs**: Reduce payload size for slower connections
- **Dashboard views**: Select only display-relevant fields
- **Data export**: Choose specific columns for reports
- **Performance optimization**: Minimize database column selection

## Behavior

- **Missing fields**: Silently ignored (no errors)
- **Invalid syntax**: Returns all fields as fallback
- **Relations**: Automatically optimized with database JOINs
- **Arrays**: Supports filtering nested collections

[Usage Guide](guide.md){ .md-button .md-button--primary }
