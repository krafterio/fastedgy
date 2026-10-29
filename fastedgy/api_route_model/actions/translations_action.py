# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Translations action: every locale of the translatable fields of a record.

A read gives the text of one locale, the one of the request. A screen editing
the translations reads them all here, then writes them back through the
regular patch, which takes a field as its translations keyed by locale.

Registered on every model holding a translatable field.
"""

from collections.abc import Callable
from functools import cache
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Path
from pydantic import create_model

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.registry import (
    RouteModelActionOptions,
    TypeModel,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    PreLoadRecordViewTransformer,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.i18n import _t
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.orm.fields import TranslationLocale, fetch_translations, translatable_fields
from fastedgy.orm.manager import BaseManager
from fastedgy.orm.query import QuerySet
from fastedgy.schemas import BaseModel as BaseSchema
from fastedgy.schemas import ErrorMessage


@cache
def translations_model(model_cls: TypeModel) -> type[BaseSchema]:
    """The schema of the translations of a model: each translatable field, its text keyed by locale."""
    fields: dict[str, Any] = {name: (dict[TranslationLocale, str], ...) for name in translatable_fields(model_cls)}

    return create_model(f"{model_cls.__name__}-Translations", __base__=BaseSchema, **fields)


class TranslationsApiRouteAction(BaseApiRouteAction):
    """Action reading every locale of the translatable fields of a record."""

    name = "translations"

    @classmethod
    def register_route(cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions) -> None:
        """Register the translations route, on a model holding a translatable field."""
        if not translatable_fields(model_cls):
            return

        router.add_api_route(
            **{
                "path": "/{item_id}/translations",
                "endpoint": generate_translations_item(model_cls),
                "methods": ["GET"],
                "summary": f"Get {model_cls.__name__} translations",
                "description": f"Retrieve every locale of the translatable fields of a single {model_cls.__name__}",
                "response_model": translations_model(model_cls),
                "responses": {404: {"model": ErrorMessage, "description": "Item not found"}},
                **options,
            }
        )


def generate_translations_item[M: BaseModel | BaseView](
    model_cls: type[M],
) -> Callable[..., Any]:
    async def translations_item(
        request: Request,
        item_id: int = Path(..., description="Item ID"),
    ) -> Any:
        return await translations_item_action(request, model_cls, item_id)

    return translations_item


async def translations_item_action[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    item_id: int,
    query: QuerySet | BaseManager | None = None,
    transformers: list[type[BaseViewTransformer]] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    query = cast(QuerySet, query or model_cls.query)
    transformers_ctx = transformers_ctx or {}
    vtr = get_service(ViewTransformerRegistry)
    transformers_ctx["item_id"] = item_id

    for transformer in vtr.get_transformers(PreLoadRecordViewTransformer, model_cls, transformers):
        query = await transformer.pre_load_record(request, query, transformers_ctx)

    resolved_id = transformers_ctx.get("item_id", item_id)

    # Read through the query of the record, so what scopes a read of it scopes this one.
    if not await query.filter(id=resolved_id).exists():
        raise HTTPException(status_code=404, detail=_t("{model} not found", model=model_cls.__name__))

    documents = await fetch_translations(model_cls, [resolved_id])

    return documents.get(resolved_id) or {name: {} for name in translatable_fields(model_cls)}


__all__ = [
    "TranslationsApiRouteAction",
    "generate_translations_item",
    "translations_item_action",
    "translations_model",
]
