# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime
from typing import Callable, Any

from fastapi import APIRouter, Body

from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.models.base import BaseModel
from fastedgy.timezone import ensure_aware
from fastedgy.api_route_model.action import (
    BaseApiRouteAction,
    generate_input_create_model,
    generate_output_model,
    clean_empty_strings,
    route_body_model,
)
from fastedgy.api_route_model.exception import handle_action_exception
from fastedgy.api_route_model.params import FieldSelectorHeader
from fastedgy.orm.field_selector import filter_selected_fields
from fastedgy.api_route_model.registry import (
    TypeModel,
    RouteModelActionOptions,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    GetViewTransformer,
    PostSaveTransformer,
    PreSaveTransformer,
)
from fastedgy.orm import transaction


class CreateApiRouteAction(BaseApiRouteAction):
    """Action for creating model instance."""

    name = "create"

    @classmethod
    def register_route(cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions) -> None:
        """Register the create route."""
        router.add_api_route(
            **{
                "path": "",
                "endpoint": generate_create_item(model_cls),
                "methods": ["POST"],
                "summary": f"Create {model_cls.__name__}",
                "description": f"Create a new {model_cls.__name__} item",
                "response_model": generate_output_model(model_cls) | dict[str, Any],
                **options,
            }
        )


def generate_create_item[M: BaseModel](
    model_cls: type[M],
) -> Callable[..., Any]:
    @route_body_model(generate_input_create_model(model_cls))
    async def create_item(
        request: Request,
        item_data: Any = Body(...),
        fields: str | None = FieldSelectorHeader(),
    ) -> Any:
        return await create_item_action(
            request,
            model_cls,
            item_data,
            fields=fields,
        )

    return create_item


@transaction
async def create_item_action[M: BaseModel](
    request: Request,
    model_cls: type[M],
    item_data: BaseModel,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> M | dict[str, Any]:
    from fastedgy.api_route_model.action import (
        is_relation_field,
        process_relational_fields,
    )

    transformers_ctx = transformers_ctx or {}

    try:
        clean_empty_strings(item_data)

        # Separate relational and scalar fields
        relational_data = {}
        scalar_data = {}

        for key, value in item_data.model_dump(exclude_unset=True, warnings=False).items():
            field = model_cls.model_fields.get(key)

            if isinstance(value, datetime):
                value = ensure_aware(value)

            if field and is_relation_field(field):
                relational_data[key] = value
            else:
                scalar_data[key] = value

        # Create instance with scalar fields only
        item = model_cls(**scalar_data)
        vtr = get_service(ViewTransformerRegistry)

        for transformer in vtr.get_transformers(PreSaveTransformer, model_cls, transformers):
            await transformer.pre_save(request, item, item_data, transformers_ctx, True)
            override = transformers_ctx.pop("override_item", None)
            if override is not None:
                item = override

        if not transformers_ctx.get("skip_save"):
            await item.save()
            await item.load()

        # Process relational fields after save
        await process_relational_fields(item, model_cls, relational_data)

        for transformer in vtr.get_transformers(PostSaveTransformer, model_cls, transformers):
            await transformer.post_save(request, item, item_data, transformers_ctx, True)

        item_dump = await filter_selected_fields(item, fields)

        for transformer in vtr.get_transformers(GetViewTransformer, model_cls, transformers):
            item_dump = await transformer.get_view(request, item, item_dump, transformers_ctx)

        return item_dump
    except Exception as e:
        handle_action_exception(e, model_cls)


__all__ = [
    "CreateApiRouteAction",
    "generate_create_item",
    "create_item_action",
]
