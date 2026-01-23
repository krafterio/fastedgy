# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Callable, Coroutine, Any

from fastapi import APIRouter, Query, HTTPException

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.params import (
    FieldSelectorHeader,
)
from fastedgy.api_route_model.registry import (
    TypeModel,
    RouteModelActionOptions,
)
from fastedgy.http import Request

from starlette.responses import Response, StreamingResponse


class ImportTemplateApiRouteAction(BaseApiRouteAction):
    """Action for import template of a model."""

    name = "import_template"

    @classmethod
    def register_route(
        cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions
    ) -> None:
        """Register the import template route."""
        router.add_api_route(
            **{
                "path": "/import/template",
                "endpoint": generate_import_template(model_cls),
                "methods": ["GET"],
                "summary": f"Import template of {model_cls.__name__}",
                "description": f"Retrieve a import template of {model_cls.__name__}",
                "responses": {
                    200: {
                        "content": {
                            "application/octet-stream": {
                                "schema": {"type": "string", "format": "binary"},
                            },
                        },
                    },
                },
                **options,
            }
        )


def generate_import_template[M = TypeModel](
    model_cls: type[M],
) -> Callable[[Request, str, int, int, str, str, str], Coroutine[Any, Any, Response]]:
    async def import_template(
        request: Request,
        format: str = Query("csv", description="Export format (csv, xlsx, ods)"),
        fields: str | None = FieldSelectorHeader(),  # type: ignore
    ) -> StreamingResponse:
        return await import_template_action(
            request,
            model_cls,
            format=format,
            fields=fields,
        )

    return import_template  # type: ignore


async def import_template_action[M = TypeModel](
    request: Request,
    model_cls: type[M],
    format: str = "csv",
    fields: str | None = None,
) -> StreamingResponse:
    """
    Import template of a model.

    Args:
        request: The HTTP request
        model_cls: The model class to import template
        format: Import template format (csv, xlsx, ods)
        fields: Field selector

    Returns:
        StreamingResponse with the import template (only field names, no data)
    """
    from fastedgy.orm.field_selector import clean_field_names_from_input
    from fastedgy.metadata_model.utils import get_field_label_from_path
    from fastedgy.dataflow.exporter import (
        generate_csv_export,
        generate_xlsx_export,
        generate_ods_export,
    )

    # Get field names to include in template
    field_names = clean_field_names_from_input(model_cls, fields)

    if not field_names or len(field_names) == 1 and field_names[0] == "id":
        # Default: exclude primary key fields
        field_names = [
            field_name
            for field_name, field in model_cls.meta.fields.items()
            if not field.exclude
            and not hasattr(field, "target")
            and not getattr(field, "primary_key", False)
        ]
    else:
        # Check if user explicitly requested ID in their input
        # clean_field_names_from_input always adds "id", so we need to check original input
        user_requested_id = False
        if fields:
            fields_list = fields.split(",") if isinstance(fields, str) else fields
            user_requested_id = "id" in [f.strip() for f in fields_list]

        # Remove ID if not explicitly requested by user
        if not user_requested_id:
            field_names = [f for f in field_names if f != "id"]

    # Get field labels for headers
    field_labels = [
        get_field_label_from_path(model_cls, field_name) for field_name in field_names
    ]

    # Generate template with only headers (no data rows)
    data_rows = []  # Empty data rows for template

    filename_base = f"{model_cls.__name__}_import_template"

    if format.lower() == "csv":
        return generate_csv_export(field_labels, data_rows, f"{filename_base}.csv")

    if format.lower() == "xlsx":
        return generate_xlsx_export(field_labels, data_rows, f"{filename_base}.xlsx")

    if format.lower() == "ods":
        return generate_ods_export(field_labels, data_rows, f"{filename_base}.ods")

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


__all__ = [
    "ImportTemplateApiRouteAction",
    "generate_import_template",
    "import_template_action",
]
