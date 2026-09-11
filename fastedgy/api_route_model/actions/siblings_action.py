# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Siblings action: the records either side of one, in a list the client describes.

A detail screen opened from a list steps to the previous and the next record of
that list. The client sends the list's own ``X-Filter`` and ``order_by``, and the
action answers with the two neighbouring ids, read in the order the list route
itself would return them: the same scoping transformers, the same filter
compiler, the same ordering, ``id`` breaking the ties.

The neighbours come from ``LAG``/``LEAD`` over that query rather than from a
``field > value`` rule, which the query builder refuses on text, choice and
boolean fields: any order the list accepts, the action follows.

The action is opt-in: enable it per model with ``@api_route_model(siblings=True)``.
"""

from collections.abc import Callable
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import func, select

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.params import FilterHeader, OrderByQuery
from fastedgy.api_route_model.registry import (
    RouteModelActionOptions,
    TypeModel,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    PrePaginateViewTransformer,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.i18n import _t
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.orm.filter import InvalidFilterError, filter_query
from fastedgy.orm.manager import BaseManager
from fastedgy.orm.order_by import inject_order_by
from fastedgy.orm.query import QuerySet
from fastedgy.schemas import BaseModel as BaseSchema


class RecordSiblings(BaseSchema):
    """The ids either side of a record, null at an end of the list or outside it."""

    previous: int | None = None
    next: int | None = None


class SiblingsApiRouteAction(BaseApiRouteAction):
    """Action locating the records before and after one (opt-in)."""

    name = "siblings"

    default_options = False

    @classmethod
    def register_route(cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions) -> None:
        """Register the siblings route."""
        router.add_api_route(
            **{
                "path": "/{item_id}/siblings",
                "endpoint": generate_siblings_item(model_cls),
                "methods": ["GET"],
                "summary": f"Get {model_cls.__name__} siblings",
                "description": (
                    f"Retrieve the {model_cls.__name__} before and after one, "
                    "in the list the filter and the ordering describe"
                ),
                "response_model": RecordSiblings,
                **options,
            }
        )


def generate_siblings_item[M: BaseModel | BaseView](
    model_cls: type[M],
) -> Callable[..., Any]:
    async def siblings_item(
        request: Request,
        item_id: int = Path(..., description="Item ID"),
        order_by: str | None = OrderByQuery(),
        filters: str | None = FilterHeader(),
    ) -> Any:
        return await siblings_item_action(
            request,
            model_cls,
            item_id,
            order_by=order_by,
            filters=filters,
        )

    return siblings_item


async def siblings_item_action[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    item_id: int,
    query: QuerySet | BaseManager | None = None,
    order_by: str | None = None,
    filters: str | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> RecordSiblings:
    transformers_ctx = transformers_ctx or {}
    vtr = get_service(ViewTransformerRegistry)

    try:
        if query is None:
            query = model_cls.query.get_queryset()
        elif isinstance(query, BaseManager):
            query = query.get_queryset()

        query = cast(QuerySet, query)
        transformers_ctx["filters"] = filters
        transformers_ctx["order_by"] = order_by

        for transformer in vtr.get_transformers(PrePaginateViewTransformer, model_cls, transformers):
            query = await transformer.pre_paginate(request, query, transformers_ctx)

        query = filter_query(query, transformers_ctx.get("filters"))
        query = inject_order_by(query, transformers_ctx.get("order_by"))

        statement, tables = await query.as_select_with_tables()
        table = tables[""][0]
        ordering = [*statement._order_by_clauses, table.c.id]

        # The list's own statement, joins and scoping included, narrowed to the
        # id and its neighbours: the order is the one the list route returns.
        ranked = (
            statement.with_only_columns(
                table.c.id.label("id"),
                func.lag(table.c.id).over(order_by=ordering).label("previous"),
                func.lead(table.c.id).over(order_by=ordering).label("next"),
            )
            .order_by(None)
            .limit(None)
            .offset(None)
            .subquery()
        )

        row = await query.database.fetch_one(select(ranked.c.previous, ranked.c.next).where(ranked.c.id == item_id))
    except InvalidFilterError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        if filters:
            raise HTTPException(status_code=422, detail=_t("Invalid filters"))
        else:
            raise

    if row is None:
        return RecordSiblings()

    return RecordSiblings(previous=row._mapping["previous"], next=row._mapping["next"])


__all__ = [
    "RecordSiblings",
    "SiblingsApiRouteAction",
    "generate_siblings_item",
    "siblings_item_action",
]
