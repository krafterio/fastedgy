# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import csv
import io
import tempfile
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any

import html2text
from fastapi import HTTPException
from starlette.responses import StreamingResponse

from fastedgy.api_route_model.params import RelationDelimiter
from fastedgy.i18n import _t
from fastedgy.metadata_model.utils import get_field_label_from_path
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.orm.field_selector import (
    clean_field_names_from_input,
    optimize_query_filter_fields,
)
from fastedgy.orm.fields import available_locales, fetch_translations, is_translatable
from fastedgy.orm.filter import (
    InvalidFilterError,
    filter_query,
)
from fastedgy.orm.order_by import inject_order_by
from fastedgy.orm.query import QuerySet
from fastedgy.orm.readable import Readable
from fastedgy.orm.utils import get_field_from_path, get_value_from_path


def parse_field_with_converter(field_expr: str) -> tuple[str, str | None]:
    """
    Parse a field expression and extract the converter if present.

    Args:
        field_expr: Field expression (e.g., "status", "status:label", "company.status:label")

    Returns:
        Tuple of (field_path, converter) where converter is None if not specified
    """
    if ":" in field_expr:
        # Split only on the last : to handle paths like "relation.field:converter"
        parts = field_expr.rsplit(":", 1)
        return parts[0], parts[1]
    return field_expr, None


def translation_locale(model_cls: type, field_path: str, converter: str | None) -> str | None:
    """The locale a column names on a translatable field of the model (``title:fr``), None on any other column."""
    if not converter or "." in field_path or converter not in available_locales():
        return None

    fields = getattr(getattr(model_cls, "meta", None), "fields", {})

    return converter if is_translatable(fields.get(field_path)) else None


def column_label(model_cls: type, field_path: str, converter: str | None) -> str:
    """The header of a column: the label of its field, ``Title (fr)`` for one locale of a translatable field."""
    label = get_field_label_from_path(model_cls, field_path)

    return f"{label} ({converter})" if translation_locale(model_cls, field_path, converter) else label


def expand_columns(
    field_names: list[str],
    expressions: Sequence[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    """The columns of the field names, each one once per converter the expressions name for it, in their order.

    A field takes several converters: one column per locale of a translatable field.
    """
    converters: dict[str, list[str | None]] = {}

    for path, converter in expressions:
        named = converters.setdefault(path, [])

        if converter not in named:
            named.append(converter)

    return [(name, converter) for name in field_names for converter in converters.get(name) or [None]]


def apply_export_converter(model_cls: type, field_path: str, value: Any, converter: str | None) -> Any:
    """
    Apply export converter to a value if the field supports it.

    Args:
        model_cls: The model class
        field_path: Path to the field (e.g., "status" or "company.status")
        value: The value to convert
        converter: Name of the converter to apply, or None

    Returns:
        The converted value, or original value if no converter applicable
    """
    if value is None:
        return None

    # Get the field from the path
    field = get_field_from_path(model_cls, field_path)

    if field is None:
        return value

    # Check if the field has an export converter class stored
    # (set by FieldExportConverter.__init_subclass__)
    # We need to use the stored class because Edgy's factory pattern
    # creates a new class that doesn't inherit our methods
    converter_class = getattr(field, "_export_converter_class", None)
    if converter_class is not None and hasattr(converter_class, "export_convert"):
        # Call export_convert as an unbound method, passing field as self
        return converter_class.export_convert(field, value, converter)

    return value


async def export_data[M: BaseModel | BaseView](
    model_cls: type[M],
    format: str,
    query: QuerySet | None = None,
    limit: int | None = None,
    offset: int = 0,
    order_by: str | None = None,
    fields: str | None = None,
    filters: str | None = None,
    relation_delimiter: RelationDelimiter = RelationDelimiter.newline,
) -> StreamingResponse:
    """
    Export data from a QuerySet to a file format (CSV, XLSX, ODS).

    Args:
        model_cls: The model class
        format: Export format ('csv', 'xlsx', 'ods')
        query: Optional QuerySet to filter data
        limit: Maximum number of records to export
        offset: Number of records to skip
        order_by: Ordering specification
        fields: Fields to include in export
        filters: Filter specification
        relation_delimiter: Delimiter for relation values (one2many, many2many)

    Returns:
        StreamingResponse with the exported file

    Raises:
        HTTPException: If format is unsupported or filters are invalid
    """
    try:
        query = query or model_cls.query.get_queryset()
        query = filter_query(query, filters)
        query = optimize_query_filter_fields(query, fields)
        query = inject_order_by(query, order_by)

        if limit is not None:
            query = query.limit(limit)

        query = query.offset(offset)
        # The SQL is built here, so that a refused filter still answers 422 before the export starts.
        await query.as_select()
    except InvalidFilterError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        if filters:
            raise HTTPException(status_code=422, detail=_t("Invalid filters"))
        else:
            raise

    # Parse field expressions to extract converters
    field_expressions = []
    if fields:
        if isinstance(fields, str):
            field_expressions = [f.strip() for f in fields.split(",") if f.strip()]
        else:
            field_expressions = fields

    # Extract field paths and converters
    field_paths_with_converters = [parse_field_with_converter(expr) for expr in field_expressions]

    # Get clean field paths (without converters) for query optimization
    field_paths_only = [path for path, _ in field_paths_with_converters]
    field_names = clean_field_names_from_input(model_cls, field_paths_only)

    if not field_names or len(field_names) == 1 and field_names[0] == "id":
        field_names = [
            field_name
            for field_name, field in model_cls.meta.fields.items()
            if not field.exclude and not hasattr(field, "target")
        ]
        # No converters for auto-generated field list
        field_paths_with_converters = [(name, None) for name in field_names]

    columns = expand_columns(field_names, field_paths_with_converters)
    translated = list(
        dict.fromkeys(name for name, converter in columns if translation_locale(model_cls, name, converter))
    )

    async def rows_of(items: list[Any]) -> list[list[str | None]]:
        documents = await fetch_translations(model_cls, [item.id for item in items], translated)
        readable = Readable()
        await readable.ask_reached(model_cls, items, field_names)
        data_rows = []

        for item in items:
            row_data = []

            for field_name, converter in columns:
                locale = translation_locale(model_cls, field_name, converter)

                if locale is not None:
                    value = documents.get(item.id, {}).get(field_name, {}).get(locale)
                else:
                    value = await get_value_from_path(item, field_name, readable)

                    if converter is not None:
                        value = apply_export_converter(model_cls, field_name, value, converter)

                row_data.append(format_value(value, relation_delimiter))

            data_rows.append(row_data)

        return data_rows

    # Read from start to end where it is consumed: Edgy binds its cursor to the context it opened in.
    async def row_batches() -> AsyncIterator[list[list[str | None]]]:
        async for batch in _batches(query):
            yield await rows_of(batch)

    field_labels = [column_label(model_cls, field_name, converter) for field_name, converter in columns]
    export_format = format.lower()

    if export_format == "csv":
        return generate_csv_export(field_labels, row_batches(), f"{model_cls.__name__}_export.csv")

    if export_format == "xlsx":
        workbook, sheet = _xlsx_workbook(field_labels)

        async for data_rows in row_batches():
            for row in data_rows:
                sheet.append(row)

        return _xlsx_response(workbook, f"{model_cls.__name__}_export.xlsx")

    if export_format == "ods":
        all_rows = [row async for data_rows in row_batches() for row in data_rows]

        return generate_ods_export(field_labels, all_rows, f"{model_cls.__name__}_export.ods")

    raise HTTPException(status_code=400, detail=_t("Unsupported export format: {format}", format=format))


EXPORT_BATCH_SIZE = 500


async def _batches(query: QuerySet) -> AsyncIterator[list[Any]]:
    """The records of the query read through one cursor, a batch at a time: an export holds one
    batch of records in memory, not all of them."""
    batch: list[Any] = []

    async for item in query.batch_size(EXPORT_BATCH_SIZE):
        batch.append(item)

        if len(batch) >= EXPORT_BATCH_SIZE:
            yield batch
            batch = []

    if batch:
        yield batch


def format_value(value: Any, relation_delimiter: RelationDelimiter = RelationDelimiter.newline) -> str | None:
    """Format a value for export based on its type."""
    if value is None:
        return None
    elif isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    elif isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M:%S")
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, list):
        separator = relation_delimiter.get_separator()
        return separator.join([str(format_value(v, relation_delimiter)) for v in value if v is not None])
    else:
        # Clean HTML tags from text values using html2text
        text_value = str(value)
        if "<" in text_value and ">" in text_value:
            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            text_value = h.handle(text_value).strip()
        return _as_text(text_value)


_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _as_text(text: str) -> str:
    return f"'{text}" if text.startswith(_FORMULA_STARTS) else text


def generate_csv_export(
    field_names: list[str],
    data_rows: Sequence[Sequence[str | None]] | AsyncIterator[list[list[str | None]]],
    filename: str,
) -> StreamingResponse:
    """Generate a CSV export file, each batch of rows sent as soon as it is written."""

    async def chunks() -> AsyncIterator[str]:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(field_names)

        if isinstance(data_rows, Sequence):
            writer.writerows(data_rows)
            yield output.getvalue()

            return

        yield output.getvalue()

        async for rows in data_rows:
            output.seek(0)
            output.truncate(0)
            writer.writerows(rows)
            yield output.getvalue()

    return StreamingResponse(
        chunks(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _xlsx_workbook(field_names: list[str]) -> tuple[Any, Any]:
    """A write-only workbook: openpyxl writes each row appended to a temporary file instead of
    holding the sheet in memory."""
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(status_code=500, detail=_t("openpyxl library is not installed"))

    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet("Export")

    for col_idx, field in enumerate(field_names, 1):
        sheet.column_dimensions[get_column_letter(col_idx)].width = max(len(field), 15)

    sheet.append(field_names)

    return workbook, sheet


def _xlsx_response(workbook: Any, filename: str) -> StreamingResponse:
    return StreamingResponse(
        _saved_chunks(workbook),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _saved_chunks(workbook: Any, size: int = 64 * 1024) -> Iterator[bytes]:
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as output:
        workbook.save(output)
        output.seek(0)

        while chunk := output.read(size):
            yield chunk


def generate_xlsx_export(
    field_names: list[str], data_rows: Sequence[Sequence[str | None]], filename: str
) -> StreamingResponse:
    """Generate an XLSX export file."""
    workbook, sheet = _xlsx_workbook(field_names)

    for row in data_rows:
        sheet.append(list(row))

    return _xlsx_response(workbook, filename)


def generate_ods_export(
    field_names: list[str], data_rows: Sequence[Sequence[str | None]], filename: str
) -> StreamingResponse:
    """Generate an ODS export file."""
    try:
        from pyexcel_ods import save_data
    except ImportError:
        raise HTTPException(status_code=500, detail=_t("pyexcel-ods library is not installed"))

    # Prepare data for pyexcel-ods
    sheet_data = [field_names]  # Header row

    # Convert None values to empty strings to avoid KeyError with pyexcel_ods
    processed_rows = []
    for row in data_rows:
        processed_row = []
        for value in row:
            processed_row.append("" if value is None else value)
        processed_rows.append(processed_row)

    sheet_data.extend(processed_rows)  # Add processed data rows

    # Create ODS file
    data = {"Export": sheet_data}
    output = io.BytesIO()
    save_data(output, data)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


__all__ = [
    "apply_export_converter",
    "column_label",
    "expand_columns",
    "export_data",
    "format_value",
    "generate_csv_export",
    "generate_ods_export",
    "generate_xlsx_export",
    "parse_field_with_converter",
    "translation_locale",
]
