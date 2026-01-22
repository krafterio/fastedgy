# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Coroutine, Any

from fastapi import APIRouter, Query, HTTPException

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.params import (
    OrderByQuery,
    FieldSelectorHeader,
    FilterHeader,
    RelationDelimiter,
    RelationDelimiterQuery,
)
from fastedgy.api_route_model.registry import (
    TypeModel,
    RouteModelActionOptions,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    PrePaginateViewTransformer,
    PostPaginateViewTransformer,
    PreExportTransformer,
    PostExportTransformer,
)
from fastedgy.dataflow.exporter import export_data
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm.filter import InvalidFilterError, filter_query
from fastedgy.orm.order_by import inject_order_by
from fastedgy.orm.field_selector import optimize_query_filter_fields
from fastedgy.orm.query import QuerySet

from starlette.responses import Response, StreamingResponse


class ExportApiRouteAction(BaseApiRouteAction):
    """Action for exporting model instances."""

    name = "export"

    @classmethod
    def register_route(
        cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions
    ) -> None:
        """Register the export route."""
        router.add_api_route(
            **{
                "path": "/export",
                "endpoint": generate_export_items(model_cls),
                "methods": ["GET"],
                "summary": f"Export {model_cls.__name__} items",
                "description": f"Retrieve a export of {model_cls.__name__} items",
                "responses": {
                    200: {
                        "content": {
                            "application/octet-stream": {
                                "schema": {"type": "string", "format": "binary"},
                            },
                        },
                    },
                },
                **options,
            }
        )


def generate_export_items[M = TypeModel](
    model_cls: type[M],
) -> Callable[
    [Request, str, int, int, str, str, str, RelationDelimiter],
    Coroutine[Any, Any, Response],
]:
    async def export_items(
        request: Request,
        format: str = Query("csv", description="Export format (csv, xlsx, ods)"),
        limit: int | None = Query(None),
        offset: int = Query(0, ge=0),
        order_by: str | None = OrderByQuery(),
        fields: str | None = FieldSelectorHeader(),
        filters: str | None = FilterHeader(),
        relation_delimiter: RelationDelimiter = RelationDelimiterQuery(),
    ) -> StreamingResponse:
        return await export_items_action(
            request,
            model_cls,
            format=format,
            limit=limit,
            offset=offset,
            order_by=order_by,
            fields=fields,
            filters=filters,
            relation_delimiter=relation_delimiter,
        )

    return export_items


async def export_items_action[M = TypeModel](
    request: Request,
    model_cls: type[M],
    format: str = "csv",
    query: QuerySet | None = None,
    limit: int | None = None,
    offset: int = 0,
    order_by: str | None = None,
    fields: str | None = None,
    filters: str | None = None,
    relation_delimiter: RelationDelimiter = RelationDelimiter.newline,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> StreamingResponse:
    """
    Export items to a file.

    Args:
        request: The HTTP request
        model_cls: The model class to export
        format: Export format (csv, xlsx, ods)
        query: Optional base QuerySet
        limit: Maximum number of items to export
        offset: Number of items to skip
        order_by: Order by expression
        fields: Field selector
        filters: Filter expression
        transformers: List of transformers to apply
        transformers_ctx: Context dictionary for transformers

    Returns:
        StreamingResponse with the export file
    """
    transformers_ctx = transformers_ctx or {}
    vtr = get_service(ViewTransformerRegistry)

    try:
        query = query or model_cls.query  # type: ignore
        query = filter_query(query, filters)
        query = optimize_query_filter_fields(query, fields)
        query = inject_order_by(query, order_by)

        # Pre-paginate transformers (for filtering, ordering, etc.)
        for transformer in vtr.get_transformers(
            PrePaginateViewTransformer, model_cls, transformers
        ):
            query = await transformer.pre_paginate(request, query, transformers_ctx)

        # Pre-export transformers
        for transformer in vtr.get_transformers(
            PreExportTransformer, model_cls, transformers
        ):
            query = await transformer.pre_export(request, query, transformers_ctx)

    except InvalidFilterError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        if filters:
            raise HTTPException(status_code=422, detail="Invalid filters")
        else:
            raise e

    # Generate export
    response = await export_data(
        model_cls,
        format,
        query,
        limit=limit,
        offset=offset,
        order_by=None,  # Already applied
        fields=fields,
        filters=None,  # Already applied
        relation_delimiter=relation_delimiter,
    )

    # Post-export transformers (can modify file content/filename)
    post_export_transformers = list(
        vtr.get_transformers(PostExportTransformer, model_cls, transformers)
    )

    if post_export_transformers:
        # Extract filename from Content-Disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        filename = (
            content_disposition.split("filename=")[-1].strip('"')
            if "filename=" in content_disposition
            else "export"
        )

        # Read the response body
        body_iterator = response.body_iterator
        file_content = b"".join([chunk async for chunk in body_iterator])

        for transformer in post_export_transformers:
            file_content, filename = await transformer.post_export(
                request, file_content, filename, transformers_ctx
            )

        # Create new response with potentially modified content
        return StreamingResponse(
            iter([file_content]),
            media_type=response.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # No post-export transformers, return response as-is from export_data
    return response


__all__ = [
    "ExportApiRouteAction",
    "generate_export_items",
    "export_items_action",
]
