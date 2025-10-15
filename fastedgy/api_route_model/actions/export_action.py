# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Coroutine, Any

from fastapi import APIRouter, Query

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.params import (
    OrderByQuery,
    FieldSelectorHeader,
    FilterHeader,
)
from fastedgy.api_route_model.registry import TypeModel, RouteModelActionOptions
from fastedgy.dataflow.exporter import export_data

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
) -> Callable[[str, int, int, str, str, str, int], Coroutine[Any, Any, Response]]:
    async def export_items(
        format: str = Query("csv", description="Export format (csv, xlsx, ods)"),
        limit: int | None = Query(None),
        offset: int = Query(0, ge=0),
        order_by: str | None = OrderByQuery(),
        fields: str | None = FieldSelectorHeader(),
        filters: str | None = FilterHeader(),
    ) -> StreamingResponse:
        query = model_cls.query

        return await export_data(
            model_cls,
            format,
            query,
            limit=limit,
            offset=offset,
            order_by=order_by,
            fields=fields,
            filters=filters,
        )

    return export_items


__all__ = [
    "ExportApiRouteAction",
    "generate_export_items",
]
