# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Coroutine, Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError, BaseModel
from pydantic_core import ErrorDetails
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request

from fastedgy.dependencies import get_service
from fastedgy.api_route_model.actions import BaseApiRouteAction, generate_input_create_model, generate_output_model, clean_empty_strings
from fastedgy.api_route_model.params import FieldSelectorHeader, filter_selected_fields
from fastedgy.api_route_model.registry import TypeModel, RouteModelActionOptions, ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import BaseViewTransformer, GetViewTransformer, PostSaveTransformer, PreSaveTransformer


class CreateApiRouteAction(BaseApiRouteAction):
    """Action for creating model instance."""

    name = "create"

    @classmethod
    def register_route(
        cls,
        router: APIRouter,
        model_cls: TypeModel,
        options: RouteModelActionOptions
    ) -> None:
        """Register the create route."""
        router.add_api_route(**{
            "path": "",
            "endpoint": generate_create_item(model_cls),
            "methods": ["POST"],
            "summary": f"Create {model_cls.__name__}",
            "description": f"Create a new {model_cls.__name__} item",
            **options,
        })


def generate_create_item[M = TypeModel](model_cls: M) -> Callable[[Request, M], Coroutine[Any, Any, M]]:
    async def create_item(
            request: Request,
            item_data: generate_input_create_model(model_cls) = Body(...),
            fields: str | None = FieldSelectorHeader(),
    ) -> type[generate_output_model(model_cls)] | dict[str, Any]:
        return await create_item_action(
            request,
            model_cls,
            item_data,
            fields=fields,
        )

    return create_item


async def create_item_action[M = TypeModel](
    request: Request,
    model_cls: M,
    item_data: BaseModel,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> type[M] | dict[str, Any]:
    transformers_ctx = transformers_ctx or {}

    try:
        clean_empty_strings(item_data)
        item = model_cls(**item_data.model_dump(exclude_unset=True))
        vtr = get_service(ViewTransformerRegistry)

        for transformer in vtr.get_transformers(PreSaveTransformer, model_cls, transformers):
            await transformer.pre_save(request, item, item_data, transformers_ctx)

        for transformer in vtr.get_transformers(PostSaveTransformer, model_cls, transformers):
            await transformer.post_save(request, item, item_data, transformers_ctx)

        await item.save()

        item_dump = await filter_selected_fields(item, fields)

        for transformer in vtr.get_transformers(GetViewTransformer, model_cls, transformers):
            item_dump = await transformer.get_view(request, item, item_dump, transformers_ctx)

        return item_dump
    except DBAPIError as e:
        if "SerializationError" in str(e.orig.__class__.__name__) or "could not serialize access" in str(e):
            raise HTTPException(
                status_code=429,
                detail="La ressource est actuellement utilisée par une autre opération. Veuillez réessayer dans quelques instants."
            )
        raise e
    except ValidationError as e:
        raise RequestValidationError(e.errors())
    except ValueError as e:
        raise RequestValidationError([ErrorDetails(
            msg=str(e),
            type='value_error',
            loc=('body',),
            input=None
        )])


__all__ = [
    "CreateApiRouteAction",
    "generate_create_item",
    "create_item_action",
]
