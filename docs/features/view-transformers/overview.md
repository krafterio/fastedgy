# View Transformers

View Transformers provide hooks to customize generated API endpoints' data presentation and access control. They are designed for **API-specific transformations**, not business logic implementation.

!!! warning "Business Logic Separation"
    View Transformers are for **API endpoint customization** only. Business logic belongs in **ORM signals**, model methods, or service layers. Using transformers for business logic is equivalent to putting business rules in API controllers.

## Key Features

- **Multiple Hook Points**: Transform data at 6 different stages of the request lifecycle
- **Query Modification**: Modify database queries before execution
- **Data Transformation**: Transform individual items or collections after retrieval
- **Save Lifecycle**: Hook into create/update operations before and after saving
- **Context Passing**: Share data between transformers through context dictionary
- **Model-Specific**: Register transformers globally or for specific models

## Transformer Types

View Transformers operate at different stages of the API request lifecycle:

### Query Stage
- **`PrePaginateViewTransformer`**: Modifies the `QuerySet` before pagination and data retrieval

### Retrieval Stage
- **`PostPaginateViewTransformer`**: Modifies the `Pagination` object after data retrieval
- **`GetViewsTransformer`**: Processes a list of items before individual transformation
- **`GetViewTransformer`**: Transforms individual item dictionaries after serialization

### Save Stage
- **`PreSaveTransformer`**: Processes items before saving (Create/Update operations)
- **`PostSaveTransformer`**: Processes items after saving (Create/Update operations)

## Request Flow Integration

View Transformers integrate seamlessly into the API Routes Generator request flow:

```
1. Request → PrePaginateViewTransformer → Query Execution
2. Query Results → GetViewsTransformer → Individual Processing
3. Each Item → GetViewTransformer → Response Serialization
4. Pagination → PostPaginateViewTransformer → Final Response
```

For Create/Update operations:
```
1. Request Data → PreSaveTransformer → Database Save
2. Saved Item → PostSaveTransformer → Response
```

## Quick Example

```python
from fastedgy.api_route_model.view_transformer import (
    PrePaginateViewTransformer,
    GetViewTransformer
)
from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm.query import QuerySet
from typing import Any, Dict

class QueryOptimizationTransformer(PrePaginateViewTransformer):
    """Optimize queries based on requested fields."""

    async def pre_paginate(
        self, request: Request, query: QuerySet, ctx: dict[str, Any]
    ) -> QuerySet:
        # Get requested fields from X-Fields header
        fields_header = request.headers.get('X-Fields', '')
        requested_fields = fields_header.split(',') if fields_header else []
        ctx['requested_fields'] = requested_fields

        # Optimize query based on requested fields
        if any('user.' in field for field in requested_fields):
            query = query.select_related('user')

        if any('category.' in field for field in requested_fields):
            query = query.select_related('category')

        return query

class DataFormattingTransformer(GetViewTransformer):
    """Format data for display purposes."""

    async def get_view(
        self, request: Request, item, item_dump: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        # Format price for display
        if 'price' in item_dump and item_dump['price'] is not None:
            item_dump['price_formatted'] = f"${float(item_dump['price']):.2f}"

        # Format dates for display
        if 'created_at' in item_dump and item_dump['created_at']:
            from datetime import datetime
            if isinstance(item_dump['created_at'], str):
                dt = datetime.fromisoformat(item_dump['created_at'].replace('Z', '+00:00'))
                item_dump['created_at_formatted'] = dt.strftime('%B %d, %Y')

        return item_dump

# Register transformers during app startup
def setup_transformers():
    vtr = get_service(ViewTransformerRegistry)

    # Register for specific model
    vtr.register_transformer(QueryOptimizationTransformer(), Product)
    vtr.register_transformer(DataFormattingTransformer(), Product)
```

## Appropriate Use Cases

### Good Uses (API Customization)
- **Data Presentation**: Format values for display (currencies, dates, numbers)
- **Data Masking**: Hide sensitive fields in responses
- **Response Enrichment**: Add computed display fields (full names, formatted values)
- **Query Optimization**: Add select_related based on requested fields
- **Response Metadata**: Add pagination info, request timestamps
- **Format Adaptation**: Customize responses for different clients (mobile, web)

### Avoid (Business Logic)
- **Data Validation**: Use Pydantic schemas or model validation
- **Business Calculations**: Use ORM signals or model methods
- **State Changes**: Use ORM signals (pre_save, post_save)
- **External Integrations**: Use background tasks or services
- **Complex Workflows**: Use service layers or domain logic

## Architecture Benefits

- **Separation of Concerns**: Keep business logic separate from route definitions
- **Reusability**: Share transformers across multiple models and endpoints
- **Testability**: Test transformation logic independently
- **Maintainability**: Centralize data transformation logic
- **Flexibility**: Combine multiple transformers for complex scenarios

## Get Started

Ready to implement custom data transformations? Learn how to create and register your first View Transformer.

[Get Started](guide.md){ .md-button .md-button--primary }
