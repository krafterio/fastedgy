# View Transformers - Detailed Guide

This guide provides detailed examples and implementation patterns for each type of View Transformer.

## Registration

View Transformers are registered through the `ViewTransformerRegistry`:

```python
from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.dependencies import get_service

# Get the registry service
vtr = get_service(ViewTransformerRegistry)

# Register for specific model
vtr.register_transformer(YourTransformer(), YourModel)

# Register globally (applies to all models)
vtr.register_transformer(GlobalTransformer())
```

## PrePaginateViewTransformer

Modifies the database query before data retrieval and pagination.

```python
from fastedgy.api_route_model.view_transformer import PrePaginateViewTransformer
from fastedgy.http import Request
from fastedgy.orm.query import QuerySet, Q
from typing import Any

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

        if 'tags' in requested_fields:
            query = query.prefetch_related('tags')

        return query

class ResponseOrderingTransformer(PrePaginateViewTransformer):
    """Apply default ordering when no explicit ordering is requested."""

    async def pre_paginate(
        self, request: Request, query: QuerySet, ctx: dict[str, Any]
    ) -> QuerySet:
        # Only apply default ordering if no order_by parameter is provided
        order_by = request.query_params.get('order_by')
        if not order_by:
            # Apply default ordering for consistent API responses
            query = query.order_by('-created_at', 'id')

        return query
```

## GetViewTransformer

Transforms individual item dictionaries after serialization.

```python
from fastedgy.api_route_model.view_transformer import GetViewTransformer
from fastedgy.http import Request
from typing import Any

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

        # Add computed display fields
        if 'first_name' in item_dump and 'last_name' in item_dump:
            item_dump['full_name'] = f"{item_dump['first_name']} {item_dump['last_name']}"

        return item_dump

class DataMaskingTransformer(GetViewTransformer):
    """Mask sensitive data for display purposes."""

    async def get_view(
        self, request: Request, item, item_dump: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        # Mask email addresses for privacy
        if 'email' in item_dump and item_dump['email']:
            email = item_dump['email']
            item_dump['email_masked'] = f"{email[:2]}***@{email.split('@')[1]}"

        # Remove internal fields from API responses
        internal_fields = ['internal_id', 'debug_info', 'system_notes']
        for field in internal_fields:
            item_dump.pop(field, None)

        return item_dump
```

## GetViewsTransformer

Processes collections of items before individual transformation.

```python
from fastedgy.api_route_model.view_transformer import GetViewsTransformer
from fastedgy.http import Request
from typing import Any

class RelatedDataCacheTransformer(GetViewsTransformer):
    """Cache related data to optimize individual item transformations."""

    async def get_views(
        self, request: Request, items: list, ctx: dict[str, Any]
    ) -> None:
        # Only fetch related data if it will be used in responses
        requested_fields = ctx.get('requested_fields', [])

        # Cache categories if category data is requested
        if any('category' in field for field in requested_fields):
            category_ids = [item.category_id for item in items if hasattr(item, 'category_id')]
            if category_ids:
                categories = await Category.objects.filter(id__in=category_ids).all()
                ctx['categories_cache'] = {cat.id: cat for cat in categories}

        # Cache user data if user fields are requested
        if any('user' in field for field in requested_fields):
            user_ids = [item.user_id for item in items if hasattr(item, 'user_id')]
            if user_ids:
                users = await User.objects.filter(id__in=user_ids).all()
                ctx['users_cache'] = {user.id: user for user in users}
```

## PostPaginateViewTransformer

Modifies the final pagination response.

```python
from fastedgy.api_route_model.view_transformer import PostPaginateViewTransformer
from fastedgy.http import Request
from fastedgy.schemas.base import Pagination
from typing import Any

class MetadataEnricherTransformer(PostPaginateViewTransformer):
    """Add metadata to pagination response."""

    async def post_paginate(
        self, request: Request, pagination: Pagination, ctx: dict[str, Any]
    ) -> None:
        # Add response metadata for client information
        pagination.metadata = {
            'request_timestamp': request.state.start_time if hasattr(request.state, 'start_time') else None,
            'response_format': 'paginated',
            'fields_selected': bool(request.headers.get('X-Fields')),
            'filters_applied': bool(request.headers.get('X-Filter')),
            'total_pages': (pagination.total + pagination.limit - 1) // pagination.limit if pagination.limit else 1
        }

class AnalyticsTrackingTransformer(PostPaginateViewTransformer):
    """Track API usage for analytics."""

    async def post_paginate(
        self, request: Request, pagination: Pagination, ctx: dict[str, Any]
    ) -> None:
        # Log API usage (fire and forget)
        import asyncio
        asyncio.create_task(self._log_usage(request, pagination))

    async def _log_usage(self, request: Request, pagination: Pagination):
        # Your analytics logging logic here
        pass
```

## PreSaveTransformer & PostSaveTransformer

Handle data during create/update operations.

```python
from fastedgy.api_route_model.view_transformer import PreSaveTransformer, PostSaveTransformer
from fastedgy.http import Request
from pydantic import BaseModel
from typing import Any

class AuditTransformer(PreSaveTransformer):
    """Add audit fields before saving."""

    async def pre_save(
        self, request: Request, item, item_data: BaseModel, ctx: dict[str, Any]
    ) -> None:
        user_id = request.headers.get('X-User-ID')

        # Set audit fields
        if hasattr(item, 'created_by') and not item.created_by:
            item.created_by = user_id

        if hasattr(item, 'updated_by'):
            item.updated_by = user_id

class NotificationTransformer(PostSaveTransformer):
    """Send notifications after successful save."""

    async def post_save(
        self, request: Request, item, item_data: BaseModel, ctx: dict[str, Any]
    ) -> None:
        # Send notification (async)
        import asyncio
        asyncio.create_task(self._send_notification(item, ctx))

    async def _send_notification(self, item, ctx: dict[str, Any]):
        # Your notification logic here
        pass
```

## PreDeleteTransformer & PostDeleteTransformer

Handle data during delete operations.

```python
from fastedgy.api_route_model.view_transformer import PreDeleteTransformer, PostDeleteTransformer
from fastedgy.http import Request
from fastapi import HTTPException
from typing import Any

class DeleteAuthorizationTransformer(PreDeleteTransformer):
    """Verify user has permission to delete item."""

    async def pre_delete(
        self, request: Request, item, ctx: dict[str, Any]
    ) -> None:
        user_id = request.headers.get('X-User-ID')

        if hasattr(item, 'user_id') and item.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

class DeleteAuditTransformer(PostDeleteTransformer):
    """Log deletion for audit trail."""

    async def post_delete(
        self, request: Request, item, ctx: dict[str, Any]
    ) -> None:
        # Log the deletion
        print(f"Item {item.id} deleted by user {request.headers.get('X-User-ID')}")
```

## PreUploadTransformer & PostUploadTransformer

Handle file uploads with storage control and path manipulation.

```python
from fastedgy.api_route_model.view_transformer import PreUploadTransformer, PostUploadTransformer
from fastedgy.http import Request
from fastapi import UploadFile, HTTPException
from typing import Any

class UploadStorageControlTransformer(PreUploadTransformer):
    """Control storage location based on user permissions."""

    async def pre_upload(
        self,
        request: Request,
        record,
        field: str,
        file: UploadFile,
        ctx: dict[str, Any],
    ) -> bool:
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/webp']
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="File type not allowed")

        # Return True for global storage, False for workspace storage
        is_admin = request.headers.get('X-User-Role') == 'admin'
        return is_admin

class UploadAuditTransformer(PostUploadTransformer):
    """Log upload activity for audit."""

    async def post_upload(
        self,
        request: Request,
        record,
        field: str,
        path: str,
        ctx: dict[str, Any],
    ) -> str:
        user_id = request.headers.get('X-User-ID')
        print(f"User {user_id} uploaded file to {path}")
        return path
```

## PreDownloadTransformer & PostDownloadTransformer

Handle file downloads with access control and path resolution.

```python
from fastedgy.api_route_model.view_transformer import PreDownloadTransformer, PostDownloadTransformer
from fastedgy.http import Request
from fastapi import HTTPException
from pathlib import Path
from typing import Any

class DownloadAuthorizationTransformer(PreDownloadTransformer):
    """Verify user has permission to download file."""

    async def pre_download(
        self,
        request: Request,
        path: str,
        ctx: dict[str, Any],
    ) -> bool:
        workspace_id = request.headers.get('X-Workspace-ID')

        # Check if path starts with 'global/' for global storage
        if path.startswith('global/'):
            return True

        # Otherwise require workspace access
        if not workspace_id:
            raise HTTPException(status_code=403, detail="Workspace required")

        return False

class DownloadAuditTransformer(PostDownloadTransformer):
    """Log file downloads for audit."""

    async def post_download(
        self,
        request: Request,
        path: str,
        served_path: Path,
        ctx: dict[str, Any],
    ) -> Path:
        user_id = request.headers.get('X-User-ID')
        print(f"User {user_id} downloaded {path}")
        return served_path
```

## Context Usage

Context dictionary allows sharing data between transformers:

```python
# In PrePaginateViewTransformer - Share data between transformers
ctx['requested_fields'] = request.headers.get('X-Fields', '').split(',')
ctx['response_format'] = request.headers.get('Accept', 'application/json')

# In GetViewTransformer - Use shared context
requested_fields = ctx.get('requested_fields', [])
if 'details' not in requested_fields:
    # Skip expensive detail formatting
```

## Best Practices

- **Performance**: Use `GetViewsTransformer` for bulk operations
- **Context**: Share expensive computations via context dictionary
- **Error Handling**: Use proper HTTP exceptions for client errors
- **Async Operations**: Use `asyncio.create_task()` for fire-and-forget operations
- **Testing**: Test transformers independently with mock requests and contexts
- **Registration**: Register transformers during app startup, not in route handlers
- **File Operations**: Return `True` from Pre*Transformer for global storage, `False` for workspace storage
- **Upload Validation**: Validate file type/size in `PreUploadTransformer` to fail fast
- **Download Security**: Check permissions in `PreDownloadTransformer` before file retrieval
- **Path Manipulation**: Use `PostUploadTransformer` and `PostDownloadTransformer` for path modifications

## Next Steps

Ready to implement View Transformers in your application?

[Back to Overview](overview.md){ .md-button }
