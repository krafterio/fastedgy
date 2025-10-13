# Query Builder - Advanced usage

This page covers advanced programmatic filtering for developers who need to build filters dynamically in Python code, rather than using the HTTP header syntax.

## Programmatic filtering

FastEdgy provides filter classes that allow you to construct filters programmatically with full type safety and IDE autocomplete support.

### Why use programmatic filters

Use programmatic filters when you need to:

- Build complex filters dynamically based on business logic
- Reuse filter expressions across multiple queries
- Leverage IDE autocomplete and type checking
- Create custom API endpoints with filtering logic
- Combine multiple filter sources programmatically

### Available classes

FastEdgy provides the following classes for programmatic filtering:

| Class | Purpose | Example |
|-------|---------|---------|
| `R` | Create a single filter rule | `R("name", "=", "value")` |
| `FilterRule` | Same as `R` (verbose form) | `FilterRule("name", "=", "value")` |
| `And` | Combine rules with AND logic | `And(rule1, rule2)` |
| `Or` | Combine rules with OR logic | `Or(rule1, rule2)` |
| `FilterCondition` | Base class for conditions | Used internally |

## Basic usage

### Simple filter rule

Use the `R` class (short for Rule) to create individual filter expressions:

```python
from fastedgy.api_route_model.params import R, filter_query
from myapp.models import Product

# Create a query
query = Product.query

# Apply a simple filter
filtered_query = filter_query(query, R("name", "=", "Laptop"))

# Execute the query
products = await filtered_query.all()
```

### Using FilterRule

`R` is an alias for `FilterRule`. Both are identical:

```python
from fastedgy.api_route_model.params import FilterRule, filter_query

# These are equivalent
filter1 = R("price", ">", 100)
filter2 = FilterRule("price", ">", 100)
```

## Combining filters

### AND conditions

Combine multiple rules that must all be true:

```python
from fastedgy.api_route_model.params import R, And, filter_query
from myapp.models import Product

query = Product.query

# Products that are active AND price >= 100
filters = And(
    R("is_active", "is true"),
    R("price", ">=", 100)
)

filtered_query = filter_query(query, filters)
products = await filtered_query.all()
```

### OR conditions

Combine multiple rules where at least one must be true:

```python
from fastedgy.api_route_model.params import R, Or, filter_query
from myapp.models import Product

query = Product.query

# Products in electronics OR books category
filters = Or(
    R("category.slug", "=", "electronics"),
    R("category.slug", "=", "books")
)

filtered_query = filter_query(query, filters)
products = await filtered_query.all()
```

## Advanced patterns

### Nested conditions

Combine AND and OR conditions for complex logic:

```python
from fastedgy.api_route_model.params import R, And, Or, filter_query
from myapp.models import Product

query = Product.query

# Active products AND (cheap OR on sale)
filters = And(
    R("is_active", "is true"),
    Or(
        R("price", "<", 50),
        R("category.slug", "=", "sale")
    )
)

filtered_query = filter_query(query, filters)
products = await filtered_query.all()
```

### Reusable filter expressions

Define filters once and reuse them:

```python
from fastedgy.api_route_model.params import R, And, filter_query
from myapp.models import Product

# Define reusable filters
active_filter = R("is_active", "is true")
affordable_filter = R("price", "<=", 100)
featured_filter = R("is_featured", "is true")

# Combine them in different ways
query1 = Product.query
affordable_active = await filter_query(query1, And(active_filter, affordable_filter)).all()

query2 = Product.query
featured_active = await filter_query(query2, And(active_filter, featured_filter)).all()
```

### Dynamic filter construction

Build filters based on runtime conditions:

```python
from fastedgy.api_route_model.params import R, And, filter_query
from myapp.models import Product

async def get_products_by_criteria(
    min_price: float | None = None,
    max_price: float | None = None,
    category: str | None = None,
):
    query = Product.query
    rules = [R("is_active", "is true")]

    if min_price is not None:
        rules.append(R("price", ">=", min_price))

    if max_price is not None:
        rules.append(R("price", "<=", max_price))

    if category is not None:
        rules.append(R("category.slug", "=", category))

    filters = And(*rules) if len(rules) > 1 else rules[0]
    filtered_query = filter_query(query, filters)
    return await filtered_query.all()

# Use it
products = await get_products_by_criteria(min_price=50, category="electronics")
```

## Using filter_query helper

The `filter_query` helper function accepts multiple filter formats:

### Supported input formats

```python
from fastedgy.api_route_model.params import R, And, filter_query
from myapp.models import Product

query = Product.query

# 1. Filter classes (NEW - what this page is about)
filter_query(query, R("name", "=", "Laptop"))
filter_query(query, And(R("price", ">", 100), R("is_active", "is true")))

# 2. Tuple format
filter_query(query, ("name", "=", "Laptop"))
filter_query(query, ("&", [("price", ">", 100), ("is_active", "is true")]))

# 3. JSON string format
filter_query(query, '["name", "=", "Laptop"]')
filter_query(query, '["&", [["price", ">", 100], ["is_active", "is true"]]]')

# 4. None (no filtering)
filter_query(query, None)
```

### Custom endpoints with filtering

Use programmatic filters in custom API endpoints:

```python
from fastapi import APIRouter, Depends
from fastedgy.api_route_model.params import R, And, filter_query
from myapp.models import Product
from myapp.schemas import ProductSchema

router = APIRouter()

@router.get("/api/products/featured")
async def get_featured_products(
    category: str | None = None,
):
    query = Product.query

    # Build filter dynamically
    rules = [
        R("is_active", "is true"),
        R("is_featured", "is true"),
    ]

    if category:
        rules.append(R("category.slug", "=", category))

    filters = And(*rules)
    query = filter_query(query, filters)

    products = await query.all()
    return [ProductSchema.model_validate(p) for p in products]
```

## Type safety benefits

Using filter classes provides several advantages over string-based filters:

### IDE autocomplete

Your IDE can suggest available methods and detect typos:

```python
from fastedgy.api_route_model.params import R

# IDE will autocomplete field names and show you the signature
rule = R(
    field="price",      # Autocomplete suggests field names
    operator=">=",      # Autocomplete suggests valid operators
    value=100
)
```

### Type checking

Static type checkers like mypy can validate your filter expressions:

```python
from fastedgy.api_route_model.params import R, And

# Type checker validates this
filters = And(
    R("name", "=", "test"),
    R("price", ">", 100)
)

# Type checker catches this error (wrong type)
# filters = And("invalid", 123)  # Type error!
```

### Refactoring safety

When you rename fields in your models, you can use IDE refactoring tools to update filter expressions automatically.

## Combining with HTTP filters

You can combine programmatic filters with HTTP header filters using `merge_filters`:

```python
from fastedgy.api_route_model.params import (
    R,
    And,
    filter_query,
    merge_filters,
    parse_filter_input,
    FilterHeader,
)
from fastapi import Depends
from myapp.models import Product

@router.get("/api/products")
async def list_products(
    x_filter: str | None = Depends(FilterHeader()),
):
    query = Product.query

    # Parse user's filter from header
    user_filters = parse_filter_input(x_filter) if x_filter else None

    # Add mandatory filter (always active products)
    system_filter = R("is_active", "is true")

    # Merge both filters with AND logic
    combined = merge_filters(system_filter, user_filters)

    # Apply to query
    query = filter_query(query, combined)
    products = await query.all()

    return products
```

## All supported operators

Programmatic filters support the same operators as HTTP filters. See the [Usage Guide](guide.md) for the complete list of operators for each field type.

### Quick reference

```python
from fastedgy.api_route_model.params import R

# Comparison
R("price", "=", 100)
R("price", "!=", 100)
R("price", "<", 100)
R("price", "<=", 100)
R("price", ">", 100)
R("price", ">=", 100)
R("price", "between", [50, 150])

# Text search
R("name", "like", "%laptop%")
R("name", "ilike", "%laptop%")
R("name", "starts with", "Mac")
R("name", "ends with", "Pro")
R("name", "contains", "book")
R("name", "icontains", "book")

# Lists
R("status", "in", ["pending", "active"])
R("status", "not in", ["archived", "deleted"])

# Boolean
R("is_active", "is true")
R("is_featured", "is false")

# Null checks
R("deleted_at", "is empty")
R("description", "is not empty")

# Relations
R("category.name", "=", "Electronics")
R("tags", "in", [1, 2, 3])

# Spatial (PostGIS)
R("location", "spatial within distance", [[2.3522, 48.8566], 5000])
R("location", "spatial distance <", [[2.3522, 48.8566], 10000])

# Vector (pgvector)
R("embedding", "cosine distance <", [0.1, [0.2, 0.3, 0.4]])
```

## Error handling

Filter classes validate operators at instantiation:

```python
from fastedgy.api_route_model.params import R

try:
    # Invalid operator
    rule = R("name", "invalid_operator", "value")
except ValueError as e:
    print(f"Error: {e}")
    # Output: Error: Operator 'invalid_operator' is not supported
```

Field validation happens when you apply filters to a query:

```python
from fastedgy.api_route_model.params import R, filter_query, InvalidFilterError
from myapp.models import Product

try:
    query = Product.query
    # Invalid field name
    filtered = filter_query(query, R("nonexistent_field", "=", "value"))
    await filtered.all()
except InvalidFilterError as e:
    print(f"Error: {e}")
    # Output: Error: Invalid filter field: nonexistent_field
```

## Best practices

### Use R for conciseness

Prefer `R` over `FilterRule` for shorter, more readable code:

```python
# Good
filters = And(
    R("is_active", "is true"),
    R("price", ">=", 100)
)

# Works but more verbose
filters = And(
    FilterRule("is_active", "is true"),
    FilterRule("price", ">=", 100)
)
```

### Extract complex filters to functions

For complex filter logic, create dedicated functions:

```python
from fastedgy.api_route_model.params import R, And, Or

def get_premium_product_filter():
    """Products that are premium: high price OR featured."""
    return Or(
        R("price", ">=", 1000),
        R("is_featured", "is true")
    )

def get_available_filter():
    """Products that are available for purchase."""
    return And(
        R("is_active", "is true"),
        R("stock", ">", 0)
    )

# Use in queries
query = Product.query
filters = And(
    get_available_filter(),
    get_premium_product_filter()
)
filtered_query = filter_query(query, filters)
products = await filtered_query.all()
```

### Document field paths for relations

When filtering by related fields, document the relationship path:

```python
from fastedgy.api_route_model.params import R

# Document the relationship for future maintainers
# Product -> Category (ForeignKey) -> name (CharField)
category_filter = R("category.name", "=", "Electronics")

# Product -> Tags (ManyToMany) -> id (IntegerField)
tags_filter = R("tags", "in", [1, 2, 3])
```

## Next steps

Now that you understand programmatic filtering, you might want to explore:

- [Usage Guide](guide.md) - Complete operator reference
- [Overview](overview.md) - Query Builder fundamentals
- [API Routes Generator](../api-routes/overview.md) - Generate APIs with built-in filtering

[Back to Overview](overview.md){ .md-button }
