# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Coroutine, Any

from fastapi import APIRouter, File, UploadFile

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.registry import TypeModel, RouteModelActionOptions
from fastedgy.dataflow.importer import (
    import_data,
    ImportResult,
    ImportErrorResponse,
    ImportFailedError,
)
from fastedgy.orm.query import QuerySet


class ImportApiRouteAction(BaseApiRouteAction):
    """Action for importing model instances from files."""

    name = "import"

    @classmethod
    def register_route(
        cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions
    ) -> None:
        """Register the import route."""
        router.add_api_route(
            **{
                "path": "/import",
                "endpoint": generate_import_items(model_cls),
                "methods": ["POST"],
                "summary": f"Import {model_cls.__name__} items",
                "description": f"Import {model_cls.__name__} items from a file (CSV, XLSX, ODS)",
                "responses": {
                    200: {"model": ImportResult},
                    400: {"model": ImportErrorResponse},
                },
                **options,
            }
        )


def generate_import_items[M = TypeModel](
    model_cls: type[M],
) -> Callable[[UploadFile], Coroutine[Any, Any, ImportResult]]:
    async def import_items(
        file: UploadFile = File(..., description="File to import (CSV, XLSX, ODS)"),
    ) -> ImportResult:
        return await import_items_action(
            model_cls,
            file,
        )

    return import_items


async def import_items_action[M = TypeModel](
    model_cls: type[M],
    file: UploadFile,
    query: QuerySet | None = None,
) -> ImportResult:
    """
    Import items from a file into the database.

    Args:
        model_cls: The model class to import into
        file: Uploaded file (CSV, XLSX, ODS)
        query: Optional base QuerySet for filtering

    Returns:
        ImportResult with statistics

    Raises:
        HTTPException: If import fails (with detailed error information)
    """
    from fastapi import HTTPException

    query = query or model_cls.query  # type: ignore

    try:
        return await import_data(
            model_cls,
            file,
            query=query,
        )
    except ImportFailedError as e:
        # Import failed (with rollback), return detailed error
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Import failed: {e.result.errors} error(s) found",
                "success": e.result.success,
                "errors": e.result.errors,
                "created": e.result.created,
                "updated": e.result.updated,
                "error_details": e.result.error_details,
            },
        )


__all__ = [
    "ImportApiRouteAction",
    "generate_import_items",
    "import_items_action",
]
