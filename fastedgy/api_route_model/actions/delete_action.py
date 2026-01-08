# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TypeVar, Callable, Any, Coroutine

from fastapi import APIRouter, Path

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.exception import handle_action_exception
from fastedgy.api_route_model.registry import (
    BaseViewTransformer,
    TypeModel,
    RouteModelActionOptions,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    PreLoadRecordViewTransformer,
    PreDeleteTransformer,
    PostDeleteTransformer,
)
from fastedgy.dependencies import get_service
from fastedgy.orm import transaction
from fastedgy.orm.query import QuerySet
from fastedgy.http import Request


M = TypeVar("M", bound=TypeModel)


class DeleteApiRouteAction(BaseApiRouteAction):
    """Action for deleting model instance."""

    name = "delete"

    @classmethod
    def register_route(
        cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions
    ) -> None:
        """Register the delete route."""
        router.add_api_route(
            **{
                "path": "/{item_id}",
                "endpoint": generate_delete_item(model_cls),
                "methods": ["DELETE"],
                "summary": f"Delete {model_cls.__name__}",
                "description": f"Delete a {model_cls.__name__} by its ID",
                "status_code": 204,
                **options,
            }
        )


def generate_delete_item(
    model_cls: M,
) -> Callable[[Request, int], Coroutine[Any, Any, None]]:
    async def delete_item(
        request: Request,
        item_id: int = Path(..., description="Item ID"),
    ) -> None:
        return await delete_item_action(
            request,
            model_cls,
            item_id,
        )

    return delete_item


@transaction
async def delete_item_action(
    request: Request,
    model_cls: M,
    item_id: int,
    query: QuerySet | None = None,
    not_found_message: str = "Enregistrement non trouvé",
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> None:
    try:
        vtr = get_service(ViewTransformerRegistry)
        transformers_ctx = transformers_ctx or {}
        query = query or model_cls.query

        for transformer in vtr.get_transformers(
            PreLoadRecordViewTransformer, model_cls, transformers
        ):
            query = await transformer.pre_load_record(request, query, transformers_ctx)

        item = await query.filter(id=item_id).get()

        for transformer in vtr.get_transformers(
            PreDeleteTransformer, model_cls, transformers
        ):
            await transformer.pre_delete(request, item, transformers_ctx)

        await item.delete()

        for transformer in vtr.get_transformers(
            PostDeleteTransformer, model_cls, transformers
        ):
            await transformer.post_delete(request, item, transformers_ctx)
    except Exception as e:
        handle_action_exception(e, model_cls, not_found_message)

    return None


__all__ = [
    "DeleteApiRouteAction",
    "generate_delete_item",
    "delete_item_action",
]
