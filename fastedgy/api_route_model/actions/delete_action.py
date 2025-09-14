# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Any, Coroutine

from fastapi import APIRouter, HTTPException, Path
from fastapi.exceptions import RequestValidationError

from fastedgy.api_route_model.actions import BaseApiRouteAction
from fastedgy.api_route_model.registry import TypeModel, RouteModelActionOptions
from fastedgy.orm.query import QuerySet
from fastedgy.orm.exceptions import ObjectNotFound

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from sqlalchemy.exc import DBAPIError


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


def generate_delete_item[M = TypeModel](
    model_cls: M,
) -> Callable[[int], Coroutine[Any, Any, None]]:
    async def delete_item(
        item_id: int = Path(..., description="Item ID"),
    ) -> None:
        return await delete_item_action(
            model_cls,
            item_id,
        )

    return delete_item


async def delete_item_action[M = TypeModel](
    model_cls: M,
    item_id: int,
    query: QuerySet | None = None,
    not_found_message: str = "Enregistrement non trouvé",
) -> None:
    try:
        query = query or model_cls.query
        item = await query.filter(id=item_id).get()

        await item.delete()
    except DBAPIError as e:
        if "SerializationError" in str(
            e.orig.__class__.__name__
        ) or "could not serialize access" in str(e):
            raise HTTPException(
                status_code=429,
                detail="La ressource est actuellement utilisée par une autre opération. Veuillez réessayer dans quelques instants.",
            )
        raise e
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=not_found_message)
    except ValidationError as e:
        raise RequestValidationError(e.errors())
    except ValueError as e:
        raise RequestValidationError(
            [ErrorDetails(msg=str(e), type="value_error", loc=("body",), input=None)]
        )

    return None


__all__ = [
    "DeleteApiRouteAction",
    "generate_delete_item",
    "delete_item_action",
]
