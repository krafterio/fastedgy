# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TypeVar, Callable, Coroutine, Any

from fastapi import APIRouter, File, UploadFile

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.registry import (
    TypeModel,
    RouteModelActionOptions,
    ViewTransformerRegistry,
)
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    PreImportTransformer,
    PostImportTransformer,
)
from fastedgy.dataflow.importer import (
    import_data,
    ImportResult,
    ImportErrorResponse,
    ImportFailedError,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.orm.query import QuerySet


M = TypeVar("M", bound=TypeModel)


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


def generate_import_items(
    model_cls: type[M],
) -> Callable[[Request, UploadFile], Coroutine[Any, Any, ImportResult]]:
    async def import_items(
        request: Request,
        file: UploadFile = File(..., description="File to import (CSV, XLSX, ODS)"),
    ) -> ImportResult:
        return await import_items_action(
            request,
            model_cls,
            file,
        )

    return import_items


async def import_items_action(
    request: Request,
    model_cls: type[M],
    file: UploadFile,
    query: QuerySet | None = None,
    transformers: list[BaseViewTransformer] | None = None,
    transformers_ctx: dict[str, Any] | None = None,
) -> ImportResult:
    """
    Import items from a file into the database.

    Args:
        request: The HTTP request
        model_cls: The model class to import into
        file: Uploaded file (CSV, XLSX, ODS)
        query: Optional base QuerySet for filtering
        transformers: List of transformers to apply
        transformers_ctx: Context dictionary for transformers

    Returns:
        ImportResult with statistics

    Raises:
        HTTPException: If import fails (with detailed error information)
    """
    from fastapi import HTTPException

    transformers_ctx = transformers_ctx or {}
    vtr = get_service(ViewTransformerRegistry)

    # Pre-import transformers (can validate or pre-process file)
    for transformer in vtr.get_transformers(
        PreImportTransformer, model_cls, transformers
    ):
        file = await transformer.pre_import(request, file, transformers_ctx)

    query = query or model_cls.query  # type: ignore

    try:
        result = await import_data(
            model_cls,
            file,
            query=query,
        )

        # Post-import transformers (called on success only)
        for transformer in vtr.get_transformers(
            PostImportTransformer, model_cls, transformers
        ):
            await transformer.post_import(request, result, transformers_ctx)

        return result

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
