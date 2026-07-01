# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Any, cast

from fastapi import APIRouter, HTTPException, Path

from fastedgy.i18n import _t
from fastedgy.schemas import ErrorMessage
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.types import ModelItem
from fastedgy.api_route_model.params import FieldSelectorHeader
from fastedgy.orm.field_selector import (
    filter_selected_fields,
    optimize_query_filter_fields,
)
from fastedgy.api_route_model.registry import (
    TypeModel,
    RouteModelActionOptions,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    GetViewTransformer,
    PreLoadRecordViewTransformer,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm.query import QuerySet
from fastedgy.orm.manager import BaseManager
from fastedgy.orm.exceptions import ObjectNotFound


class GetApiRouteAction(BaseApiRouteAction):
    """Action for retrieveing model instance."""

    name = "get"

    @classmethod
    def register_route(cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions) -> None:
        """Register the get route."""
        router.add_api_route(
            **{
                "path": "/{item_id}",
                "endpoint": generate_get_item(model_cls),
                "methods": ["GET"],
                "summary": f"Get {model_cls.__name__}",
                "description": f"Retrieve a single {model_cls.__name__} by its ID",
                "response_model": ModelItem[model_cls],
                "responses": {404: {"model": ErrorMessage, "description": "Item not found"}},
                **options,
            }
        )


def generate_get_item[M: BaseModel | BaseView](
    model_cls: type[M],
) -> Callable[..., Any]:
    async def get_item(
        request: Request,
        item_id: int = Path(..., description="Item ID"),
        fields: str | None = FieldSelectorHeader(),
    ) -> Any:
        return await get_item_action(
            request,
            model_cls,
            item_id,
            fields=fields,
        )

    return get_item


async def get_item_action[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    item_id: int,
    query: QuerySet | BaseManager | None = None,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> M | dict[str, Any]:
    query = cast(QuerySet, query or model_cls.query)
    query = optimize_query_filter_fields(query, fields)
    transformers_ctx = transformers_ctx or {}
    vtr = get_service(ViewTransformerRegistry)

    try:
        transformers_ctx["item_id"] = item_id
        for transformer in vtr.get_transformers(PreLoadRecordViewTransformer, model_cls, transformers):
            query = await transformer.pre_load_record(request, query, transformers_ctx)

        resolved_id = transformers_ctx.get("item_id", item_id)
        item = await query.filter(id=resolved_id).get()

        return await view_item_action(request, model_cls, item, fields, transformers, transformers_ctx)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=_t("{model} not found", model=model_cls.__name__))


async def view_item_action[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    item: M,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> M | dict[str, Any]:
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
