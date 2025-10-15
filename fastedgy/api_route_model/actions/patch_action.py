# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Any, Coroutine

from fastapi import APIRouter, Path, Body

from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm import transaction
from fastedgy.orm.query import QuerySet
from fastedgy.api_route_model.action import (
    BaseApiRouteAction,
    generate_input_patch_model,
    generate_output_model,
    clean_empty_strings,
)
from fastedgy.api_route_model.exception import handle_action_exception
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
    PostSaveTransformer,
    PreLoadRecordViewTransformer,
    PreSaveTransformer,
)


class PatchApiRouteAction(BaseApiRouteAction):
    """Action for patching model instance."""

    name = "patch"

    @classmethod
    def register_route(
        cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions
    ) -> None:
        """Register the patch route."""
        router.add_api_route(
            **{
                "path": "/{item_id}",
                "endpoint": generate_patch_item(model_cls),
                "methods": ["PATCH"],
                "summary": f"Update {model_cls.__name__}",
                "description": f"Update an existing {model_cls.__name__} by its ID",
                **options,
            }
        )


def generate_patch_item[M = TypeModel](
    model_cls: M,
) -> Callable[[Request, int, M], Coroutine[Any, Any, M | dict[str, Any]]]:
    async def patch_item(
        request: Request,
        item_id: int = Path(..., description="Item ID"),
        item_data: generate_input_patch_model(model_cls) = Body(),
        fields: str | None = FieldSelectorHeader(),
    ) -> generate_output_model(model_cls) | dict[str, Any]:
        return await patch_item_action(
            request,
            model_cls,
            item_id,
            item_data,
            fields=fields,
        )

    return patch_item


@transaction
async def patch_item_action[M = TypeModel](
    request: Request,
    model_cls: M,
    item_id: int,
    item_data: type[M],
    query: QuerySet | None = None,
    fields: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> M | dict[str, Any]:
    from fastedgy.api_route_model.action import (
        is_relation_field,
        process_relational_fields,
    )

    query = query or model_cls.query
    query = query.filter(id=item_id)
    query = optimize_query_filter_fields(query, fields)
    transformers_ctx = transformers_ctx or {}
    vtr = get_service(ViewTransformerRegistry)

    try:
        for transformer in vtr.get_transformers(
            PreLoadRecordViewTransformer, model_cls, transformers
        ):
            query = await transformer.pre_load_record(request, query, transformers_ctx)

        item = await query.get()

        # Separate relational and scalar fields
        relational_data = {}
        scalar_data = {}

        clean_empty_strings(item_data)
        for key in item_data.model_fields_set:
            value = getattr(item_data, key)
            field = model_cls.model_fields.get(key)

            if field and is_relation_field(field):
                relational_data[key] = value
            else:
                scalar_data[key] = value

        # Update scalar fields
        for key, value in scalar_data.items():
            setattr(item, key, value)

        for transformer in vtr.get_transformers(
            PreSaveTransformer, model_cls, transformers
        ):
            await transformer.pre_save(request, item, item_data, transformers_ctx)

        await item.save()

        # Process relational fields after save
        await process_relational_fields(item, model_cls, relational_data)

        for transformer in vtr.get_transformers(
            PostSaveTransformer, model_cls, transformers
        ):
            await transformer.post_save(request, item, item_data, transformers_ctx)

        item_dump = await filter_selected_fields(item, fields)

        for transformer in vtr.get_transformers(
            GetViewTransformer, model_cls, transformers
        ):
            item_dump = await transformer.get_view(
                request, item, item_dump, transformers_ctx
            )

        return item_dump
    except Exception as e:
        handle_action_exception(e, model_cls)


__all__ = [
    "PatchApiRouteAction",
    "generate_patch_item",
    "patch_item_action",
]
