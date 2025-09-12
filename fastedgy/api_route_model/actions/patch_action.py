# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Any, Coroutine

from edgy import ObjectNotFound, QuerySet
from fastapi import APIRouter, HTTPException, Path, Body
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pydantic_core import ErrorDetails
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request

from fastedgy.dependencies import get_service
from fastedgy.api_route_model.actions import BaseApiRouteAction, generate_input_patch_model, generate_output_model, clean_empty_strings
from fastedgy.api_route_model.params import FieldSelectorHeader, filter_selected_fields, optimize_query_filter_fields
from fastedgy.api_route_model.registry import TypeModel, RouteModelActionOptions, ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import BaseViewTransformer, GetViewTransformer, PostSaveTransformer, PreSaveTransformer


class PatchApiRouteAction(BaseApiRouteAction):
    """Action for patching model instance."""

    name = "patch"

    @classmethod
    def register_route(
        cls,
        router: APIRouter,
        model_cls: TypeModel,
        options: RouteModelActionOptions
    ) -> None:
        """Register the patch route."""
        router.add_api_route(**{
            "path": "/{item_id}",
            "endpoint": generate_patch_item(model_cls),
            "methods": ["PATCH"],
            "summary": f"Update {model_cls.__name__}",
            "description": f"Update an existing {model_cls.__name__} by its ID",
            **options,
        })


def generate_patch_item[M = TypeModel](model_cls: M) -> Callable[[Request, int, M], Coroutine[Any, Any, M]]:
    async def patch_item(
            request: Request,
            item_id: int = Path(..., description="Item ID"),
            item_data: generate_input_patch_model(model_cls) = Body(),
            fields: str | None = FieldSelectorHeader(),
    ) -> type[generate_output_model(model_cls)] | dict[str, Any]:
        return await patch_item_action(
            request,
            model_cls,
            item_id,
            item_data,
            fields=fields,
        )

    return patch_item


async def patch_item_action[M = TypeModel](
    request: Request,
    model_cls: M,
    item_id: int,
    item_data: type[M],
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
        vtr = get_service(ViewTransformerRegistry)

        clean_empty_strings(item_data)
        for key in item_data.model_fields_set:
            value = getattr(item_data, key)
            setattr(item, key, value)

        for transformer in vtr.get_transformers(PreSaveTransformer, model_cls, transformers):
            await transformer.pre_save(request, item, item_data, transformers_ctx)

        await item.save()

        for transformer in vtr.get_transformers(PostSaveTransformer, model_cls, transformers):
            await transformer.post_save(request, item, item_data, transformers_ctx)

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
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=f"{model_cls.__name__} not found")
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
    "PatchApiRouteAction",
    "generate_patch_item",
    "patch_item_action",
]
