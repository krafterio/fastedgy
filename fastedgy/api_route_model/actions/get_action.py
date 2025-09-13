# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Coroutine, Any

from fastapi import APIRouter, HTTPException, Path

from fastedgy.api_route_model.actions import BaseApiRouteAction, generate_output_model
from fastedgy.api_route_model.params import FieldSelectorHeader, filter_selected_fields, optimize_query_filter_fields
from fastedgy.api_route_model.registry import TypeModel, RouteModelActionOptions, ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import BaseViewTransformer, GetViewTransformer
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm.query import QuerySet
from fastedgy.orm.exceptions import ObjectNotFound


class GetApiRouteAction(BaseApiRouteAction):
    """Action for retrieveing model instance."""

    name = "get"

    @classmethod
    def register_route(
        cls,
        router: APIRouter,
        model_cls: TypeModel,
        options: RouteModelActionOptions
    ) -> None:
        """Register the get route."""
        router.add_api_route(**{
            "path": "/{item_id}",
            "endpoint": generate_get_item(model_cls),
            "methods": ["GET"],
            "summary": f"Get {model_cls.__name__}",
            "description": f"Retrieve a single {model_cls.__name__} by its ID",
            **options,
        })


def generate_get_item[M = TypeModel](model_cls: M) -> Callable[[Request, int], Coroutine[Any, Any, M]]:
    async def get_item(
            request: Request,
            item_id: int = Path(..., description="Item ID"),
            fields: str | None = FieldSelectorHeader(),
    ) -> type[generate_output_model(model_cls)] | dict[str, Any]:
        return await get_item_action(
            request,
            model_cls,
            item_id,
            fields=fields,
        )

    return get_item


async def get_item_action[M = TypeModel](
    request: Request,
    model_cls: M,
    item_id: int,
    query: QuerySet | None = None,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> type[M] | dict[str, Any]:
    query = query or model_cls.query
    query = query.filter(id=item_id)
    query = optimize_query_filter_fields(query, fields)
    transformers_ctx = transformers_ctx or {}

    try:
        item = await query.get()

        return await view_item_action(request, model_cls, item, fields, transformers, transformers_ctx)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=f"{model_cls.__name__} not found")


async def view_item_action[M = TypeModel](
    request: Request,
    model_cls: M,
    item,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transformers_ctx = transformers_ctx or {}
    item_dump = await filter_selected_fields(item, fields)
    vtr = get_service(ViewTransformerRegistry)

    for transformer in vtr.get_transformers(GetViewTransformer, model_cls, transformers):
        item_dump = await transformer.get_view(request, item, item_dump, transformers_ctx)

    return item_dump


__all__ = [
    "GetApiRouteAction",
    "generate_get_item",
    "get_item_action",
    "view_item_action",
]
