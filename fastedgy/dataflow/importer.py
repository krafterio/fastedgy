# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
import csv
from datetime import date, datetime
from enum import Enum
from typing import Any, TYPE_CHECKING

from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError

from fastedgy.i18n import _t
from fastedgy.orm import transaction
from fastedgy.schemas import BaseModel, ValidationError

from fastedgy.metadata_model.utils import get_field_label_from_path
from fastedgy.orm.query import QuerySet

if TYPE_CHECKING:
    from fastapi import UploadFile
    from fastedgy.orm import Model


class ImportResult(BaseModel):
    """Result of an import operation."""

    success: int = 0
    errors: int = 0
    created: int = 0
    updated: int = 0
    error_details: list[dict[str, Any]] = []


class ImportErrorResponse(BaseModel):
    """Error response when import fails."""

    message: str
    success: int
    errors: int
    created: int
    updated: int
    error_details: list[dict[str, Any]]


class ImportFailedError(Exception):
    """Exception raised when import fails with errors."""

    def __init__(self, result: ImportResult):
        self.result = result
        super().__init__(
            f"Import failed: {result.errors} error(s) found, "
            f"{result.success} row(s) processed successfully"
        )


def _format_error_message(error: Exception) -> str:
    """
    Format error message to be user-friendly.

    Extracts essential information from Pydantic ValidationError and other exceptions.
    """
    if isinstance(error, ValidationError):
        # Parse Pydantic validation errors
        errors = []
        for err in error.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            msg = err["msg"]
            errors.append(f"{field}: {msg}")
        return "; ".join(errors)

    # For other exceptions, return the message as-is
    return str(error)


def _format_db_error_message(
    error: Exception, model_cls: type["Model"] | None = None
) -> str:
    """
    Format database error messages to be user-friendly.

    Handles IntegrityError, DataError, ProgrammingError from SQLAlchemy.
    Uses translation for localized messages.

    Args:
        error: The exception to format
        model_cls: Optional model class to get field labels from metadata
    """

    def _get_field_label(field_name: str) -> str:
        """Get field label from model metadata, or return field name as fallback."""
        if model_cls and field_name:
            try:
                return get_field_label_from_path(model_cls, field_name)
            except Exception:
                pass
        return field_name

    # Handle integrity errors (constraint violations)
    if isinstance(error, IntegrityError):
        error_msg = str(error.orig) if hasattr(error, "orig") else str(error)

        # Handle unique constraint violations
        if "unique constraint" in error_msg.lower() or "UniqueViolationError" in str(
            getattr(error, "orig", error).__class__.__name__
        ):
            field_name = None
            if "Key (" in error_msg:
                field_part = error_msg.split("Key (")[1].split(")")[0]
                field_name = field_part

            if field_name:
                field_label = _get_field_label(field_name)
                return str(
                    _t(
                        "An entry with this value already exists for the field '{field_name}'.",
                        field_name=field_label,
                    )
                )
            return str(_t("This entry already exists in the database."))

        # Handle foreign key violations
        if (
            "foreign key constraint" in error_msg.lower()
            or "ForeignKeyViolationError"
            in str(getattr(error, "orig", error).__class__.__name__)
        ):
            return str(
                _t("The reference to a related resource is invalid or does not exist.")
            )

        # Handle check constraint violations
        if "check constraint" in error_msg.lower() or "CheckViolationError" in str(
            getattr(error, "orig", error).__class__.__name__
        ):
            return str(
                _t("The provided data does not meet the validation constraints.")
            )

        # Handle not null constraint violations
        if (
            "not-null constraint" in error_msg.lower()
            or "null value" in error_msg.lower()
            or "NotNullViolationError"
            in str(getattr(error, "orig", error).__class__.__name__)
        ):
            # Try to extract field name from error message
            # PostgreSQL format: null value in column "field_name" violates not-null constraint
            field_name = None
            if 'column "' in error_msg:
                field_name = error_msg.split('column "')[1].split('"')[0]
            elif "column " in error_msg.lower():
                # Alternative format without quotes
                parts = error_msg.lower().split("column ")
                if len(parts) > 1:
                    field_name = parts[1].split()[0].strip("\"'")

            if field_name:
                field_label = _get_field_label(field_name)
                return str(
                    _t(
                        "A required field is missing: '{field_name}'.",
                        field_name=field_label,
                    )
                )
            return str(_t("A required field is missing."))

        # Generic integrity error
        return str(_t("The provided data violates a database integrity constraint."))

    # Handle data errors (type mismatches, invalid values)
    if isinstance(error, DataError):
        error_msg = str(error.orig) if hasattr(error, "orig") else str(error)

        if "invalid input syntax" in error_msg.lower():
            return str(_t("Invalid data format. Please check the values in your file."))

        if "numeric field overflow" in error_msg.lower():
            return str(_t("A numeric value is too large for the field."))

        return str(_t("The data format is invalid. Please check your values."))

    # Handle programming errors (SQL errors, type mismatches in queries)
    if isinstance(error, ProgrammingError):
        error_msg = str(error.orig) if hasattr(error, "orig") else str(error)

        if "operator does not exist" in error_msg.lower():
            return str(
                _t("Invalid data type for the field. Please check the value format.")
            )

        if "column" in error_msg.lower() and "does not exist" in error_msg.lower():
            return str(
                _t("A field referenced in the file does not exist in the database.")
            )

        return str(
            _t("An error occurred processing the data. Please verify the file format.")
        )

    # Fallback: return original message
    return str(error)


@transaction
async def import_data[M](
    model_cls: type[M],
    file: "UploadFile",
    query: QuerySet | None = None,
) -> ImportResult:
    """
    Import data from a file (CSV, XLSX, ODS) into the database.

    Transaction behavior:
    - All operations are wrapped in a database transaction
    - If all rows are processed successfully (or with expected errors), COMMIT
    - If a critical error occurs, ROLLBACK all changes

    Logic:
    - If a column corresponds to primary key or unique field and value is filled:
      → Try to find existing record. If found: UPDATE, if not found: ERROR
    - If identifier column value is empty or no identifier column exists:
      → CREATE new record

    Args:
        model_cls: The model class to import into
        file: Uploaded file (CSV, XLSX, ODS)
        query: Optional base QuerySet for filtering (e.g., workspace filtering)

    Returns:
        ImportResult with statistics and error details

    Raises:
        HTTPException: If file format is unsupported or file is invalid
    """
    from fastapi import HTTPException

    # Parse file based on extension
    filename = file.filename.lower() if file.filename else ""

    if filename.endswith(".csv"):
        rows = await parse_csv_file(file)
    elif filename.endswith(".xlsx"):
        rows = await parse_xlsx_file(file)
    elif filename.endswith(".ods"):
        rows = await parse_ods_file(file)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: CSV, XLSX, ODS",
        )

    if not rows:
        raise HTTPException(status_code=400, detail="File is empty or has no data rows")

    # Extract headers (first row)
    headers = rows[0]
    data_rows = rows[1:]

    # Map column headers to field names
    field_mapping = map_columns(headers, model_cls)

    # Detect identifier field (primary key or unique field)
    identifier_field = detect_identifier_field(model_cls, field_mapping)

    result = ImportResult()

    # Process each data row (transaction handled by @transaction decorator)
    for row_idx, row in enumerate(data_rows, start=2):  # Start at 2 (header is row 1)
        try:
            await process_row(
                model_cls, row, headers, field_mapping, identifier_field, query, result
            )
        except Exception as e:
            result.errors += 1
            # Clean error message (extract essential info from Pydantic ValidationError)
            error_message = _format_error_message(e)
            result.error_details.append(
                {
                    "row": row_idx,
                    "error": error_message,
                    "data": dict(zip(headers, row)),
                }
            )

    # If any errors occurred, raise an exception to trigger rollback
    if result.errors > 0:
        raise ImportFailedError(result)

    return result


async def parse_csv_file(file: "UploadFile") -> list[list[str]]:
    """Parse CSV file and return rows."""
    content = await file.read()
    text = content.decode("utf-8-sig")  # Handle BOM
    reader = csv.reader(io.StringIO(text))
    return list(reader)


async def parse_xlsx_file(file: "UploadFile") -> list[list[str]]:
    """Parse XLSX file and return rows."""
    from fastapi import HTTPException

    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl library is not installed")

    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active

    rows = []
    for row in ws.iter_rows(values_only=True):
        # Convert all values to strings, handle None
        rows.append([str(cell) if cell is not None else "" for cell in row])

    return rows


async def parse_ods_file(file: "UploadFile") -> list[list[str]]:
    """Parse ODS file and return rows."""
    from fastapi import HTTPException

    try:
        from pyexcel_ods3 import get_data
    except ImportError:
        raise HTTPException(
            status_code=500, detail="pyexcel-ods3 library is not installed"
        )

    content = await file.read()
    data = get_data(io.BytesIO(content))

    # Get first sheet
    sheet_name = list(data.keys())[0]
    rows = data[sheet_name]

    # Convert all values to strings
    return [[str(cell) if cell is not None else "" for cell in row] for row in rows]


def map_columns(headers: list[str], model_cls: type["Model"]) -> dict[str, str]:
    """
    Map column headers to field names (technical or label).

    Supports:
    - Technical names: "name", "user.email"
    - Labels: "Name", "User / Email"

    Args:
        headers: List of column headers from file
        model_cls: The model class

    Returns:
        Dict mapping header → field_name (e.g., {"User / Email": "user.email"})
    """
    mapping = {}

    for header in headers:
        if not header or not header.strip():
            continue

        header_clean = header.strip()

        # Try direct match with field name (technical)
        if "." in header_clean:
            # Nested field (e.g., "user.email")
            mapping[header] = header_clean
        elif header_clean in model_cls.meta.fields:
            # Direct field name
            mapping[header] = header_clean
        else:
            # Try to find by label
            field_name = find_field_by_label(model_cls, header_clean)
            if field_name:
                mapping[header] = field_name

    return mapping


def find_field_by_label(model_cls: type["Model"], label: str) -> str | None:
    """Find field name by its label."""
    # Try exact match with label
    for field_name in model_cls.meta.fields:
        field_label = get_field_label_from_path(model_cls, field_name)
        if field_label.lower() == label.lower():
            return field_name

        # Also try with relation separator (e.g., "User / Email")
        if " / " in label:
            parts = label.split(" / ")
            # Try to build field path from labels
            current_model = model_cls
            field_path = []

            for part in parts:
                found = False
                for fname in current_model.meta.fields:
                    flabel = get_field_label_from_path(current_model, fname)
                    if flabel.lower() == part.lower():
                        field_path.append(fname)
                        field = current_model.meta.fields[fname]

                        # Navigate to related model
                        if hasattr(field, "target"):
                            current_model = field.target
                        elif hasattr(field, "related_from"):
                            current_model = field.related_from

                        found = True
                        break

                if not found:
                    break

            if len(field_path) == len(parts):
                return ".".join(field_path)

    return None


def detect_identifier_field(
    model_cls: type["Model"], field_mapping: dict[str, str]
) -> str | None:
    """
    Detect the identifier field (primary key or unique field) from mapped columns.

    Priority:
    1. Primary key field
    2. First unique field found

    Args:
        model_cls: The model class
        field_mapping: Dict mapping header → field_name

    Returns:
        Field name to use as identifier, or None if no identifier found
    """
    mapped_fields = set(field_mapping.values())

    # Check for primary key
    for field_name, field in model_cls.meta.fields.items():
        if field_name in mapped_fields and getattr(field, "primary_key", False):
            return field_name

    # Check for unique fields
    for field_name, field in model_cls.meta.fields.items():
        if field_name in mapped_fields and getattr(field, "unique", False):
            return field_name

    return None


async def process_row(
    model_cls: type["Model"],
    row: list[str],
    headers: list[str],
    field_mapping: dict[str, str],
    identifier_field: str | None,
    query: QuerySet | None,
    result: ImportResult,
) -> None:
    """
    Process a single row and create or update record.

    Args:
        model_cls: The model class
        row: Row data
        headers: Column headers
        field_mapping: Dict mapping header → field_name
        identifier_field: Field to use for identification (pk or unique)
        query: Optional base QuerySet
        result: ImportResult to update
    """
    row_data = dict(zip(headers, row))

    # Check if we should UPDATE or CREATE
    identifier_value = None
    identifier_value_raw = None
    identifier_field_obj = None
    if identifier_field:
        # Find the header that maps to the identifier field
        for header, field_name in field_mapping.items():
            if field_name == identifier_field:
                identifier_value_raw = row_data.get(header, "").strip()
                identifier_field_obj = model_cls.meta.fields.get(identifier_field)
                break

        # Convert identifier to correct type before querying
        if identifier_value_raw and identifier_field_obj:
            identifier_value = convert_value(identifier_value_raw, identifier_field_obj)
            if identifier_value is None:
                # Conversion failed - invalid format
                field_label = get_field_label_from_path(model_cls, identifier_field)
                raise ValueError(
                    str(
                        _t(
                            "Invalid value '{value}' for field '{field}'. Please check the format.",
                            value=identifier_value_raw,
                            field=field_label,
                        )
                    )
                )
        elif identifier_value_raw:
            # No field object found, use raw value as fallback
            identifier_value = identifier_value_raw

    # Determine action: UPDATE if identifier is filled, CREATE otherwise
    existing_record = None
    if identifier_value:
        # Try to find existing record
        try:
            q = query or model_cls.query
            existing_record = await q.filter(
                **{identifier_field: identifier_value}
            ).first()
        except (DataError, ProgrammingError) as e:
            # Handle type mismatch errors gracefully
            raise ValueError(_format_db_error_message(e, model_cls))

        if not existing_record:
            field_label = get_field_label_from_path(model_cls, identifier_field)
            raise ValueError(
                str(
                    _t(
                        "No record found with {field} = '{value}'.",
                        field=field_label,
                        value=identifier_value_raw,
                    )
                )
            )

    # Convert row data to model fields
    model_data = {}
    relational_data = {}

    for header, value in row_data.items():
        field_name = field_mapping.get(header)
        if not field_name:
            continue

        # Skip identifier field for CREATE (it will be auto-generated)
        if field_name == identifier_field and not existing_record:
            continue

        # Handle nested fields (relations)
        if "." in field_name:
            await process_relational_field(
                model_cls, field_name, value, model_data, relational_data
            )
        else:
            field = model_cls.meta.fields.get(field_name)
            if not field:
                continue

            # Check if it's a direct relational field (Many2one, Many2many, One2many)
            if is_relation_field(field):
                await process_relational_field(
                    model_cls, field_name, value, model_data, relational_data
                )
            else:
                # Regular scalar field
                converted_value = convert_value(value, field)
                model_data[field_name] = converted_value

    # Create or update record
    if existing_record:
        # UPDATE using query.update() for proper transaction handling
        try:
            q = query or model_cls.query
            await q.filter(**{identifier_field: identifier_value}).update(**model_data)

            # Refresh the record to get updated values
            existing_record = await q.filter(
                **{identifier_field: identifier_value}
            ).first()

            # Handle relational fields
            await process_relational_data(existing_record, relational_data)
        except (IntegrityError, DataError, ProgrammingError) as e:
            raise ValueError(_format_db_error_message(e, model_cls))

        result.updated += 1
    else:
        # CREATE using query.create() for proper transaction handling
        try:
            q = query or model_cls.query
            record = await q.create(**model_data)

            # Handle relational fields
            await process_relational_data(record, relational_data)
        except (IntegrityError, DataError, ProgrammingError) as e:
            raise ValueError(_format_db_error_message(e, model_cls))

        result.created += 1

    result.success += 1


def is_relation_field(field) -> bool:
    """Check if a field is relational (Many2one, Many2many, One2many)."""
    from edgy.core.db.relationships.related_field import RelatedField

    return (
        getattr(field, "is_m2m", False) is True
        or isinstance(field, RelatedField)
        or hasattr(field, "target")
    )


async def process_relational_field(
    model_cls: type["Model"],
    field_path: str,
    value: str,
    model_data: dict[str, Any],
    relational_data: dict[str, Any],
) -> None:
    """
    Process a relational field value.

    Supports:
    - Many2one: "user.email" → find user by email, store ID in model_data
    - Many2many/One2many: multiple values separated by newlines, store IDs in relational_data

    Args:
        model_cls: The model class
        field_path: Field path (e.g., "user.email", "tags")
        value: String value from file
        model_data: Dict to populate with scalar field values (including Many2one IDs)
        relational_data: Dict to populate with M2M/O2M relation IDs
    """
    if not value or not value.strip():
        return

    parts = field_path.split(".")
    base_field = parts[0]

    field = model_cls.meta.fields.get(base_field)
    if not field:
        return

    # Determine if it's Many2one, Many2many, or One2many
    is_many2one = hasattr(field, "target") and not getattr(field, "is_m2m", False)
    is_many2many_or_one2many = getattr(field, "is_m2m", False) or hasattr(
        field, "related_from"
    )

    if is_many2one:
        # Many2one: single value → store in model_data (for object creation)
        unique_field = parts[1] if len(parts) > 1 else "id"
        related_id = await resolve_relation_value(field, value.strip(), unique_field)
        if related_id:
            model_data[base_field] = related_id

    elif is_many2many_or_one2many:
        # Many2many or One2many: multiple values separated by newlines → store in relational_data
        unique_field = parts[1] if len(parts) > 1 else "id"
        values = [v.strip() for v in value.split("\n") if v.strip()]
        related_ids = []

        for val in values:
            related_id = await resolve_relation_value(field, val, unique_field)
            if related_id:
                related_ids.append(related_id)

        if related_ids:
            relational_data[base_field] = related_ids


async def resolve_relation_value(
    field, value: str, unique_field: str = "id"
) -> int | None:
    """
    Resolve a relation value to its ID.

    Args:
        field: The field definition
        value: String value (ID or unique field value)
        unique_field: Field to use for lookup (default: "id")

    Returns:
        Related record ID, or None if not found
    """
    # Get related model
    if hasattr(field, "target"):
        related_model = field.target
    elif hasattr(field, "related_from"):
        related_model = field.related_from
    else:
        return None

    # Try to convert value to appropriate type
    if unique_field == "id":
        # Direct ID lookup
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    else:
        # Lookup by unique field
        record = await related_model.query.filter(**{unique_field: value}).first()
        return record.id if record else None


async def process_relational_data(
    record: "Model", relational_data: dict[str, Any]
) -> None:
    """
    Apply relational data to a record after it's saved.
    Only handles Many2many and One2many relations (Many2one are in model_data).

    Args:
        record: The saved record
        relational_data: Dict of field_name → list of IDs (for M2M/O2M only)
    """
    for field_name, value in relational_data.items():
        if isinstance(value, list):
            # Many2many or One2many: set all relations
            relation = getattr(record, field_name)
            # Clear existing and add new
            await relation.clear()
            for related_id in value:
                await relation.add(related_id)


def convert_value(value: str, field) -> Any:
    """
    Convert a string value to the appropriate Python type based on field type.

    Args:
        value: String value from file
        field: Field definition

    Returns:
        Converted value
    """
    if not value or not value.strip():
        return None

    value = value.strip()

    # Get field type
    field_type = getattr(field, "field_type", None) or type(field).__name__

    # Boolean
    if "bool" in str(field_type).lower():
        return value.lower() in ("true", "1", "yes", "oui", "t", "y")

    # Integer
    if "int" in str(field_type).lower() and "integer" not in str(field_type).lower():
        try:
            return int(float(value))  # Handle "5.0" → 5
        except (ValueError, TypeError):
            return None

    # Float
    if "float" in str(field_type).lower() or "decimal" in str(field_type).lower():
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # Date
    if "date" in str(field_type).lower() and "datetime" not in str(field_type).lower():
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    # Datetime
    if "datetime" in str(field_type).lower():
        try:
            # Try common datetime formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    # Enum
    if hasattr(field, "choices") or "Enum" in str(field_type):
        # Try to match enum value
        if hasattr(field, "choices"):
            for choice in field.choices:
                if isinstance(choice, Enum):
                    if choice.value == value or choice.name == value:
                        return choice
        return value

    # Default: return as string
    return value


__all__ = [
    "ImportResult",
    "ImportErrorResponse",
    "ImportFailedError",
    "import_data",
    "parse_csv_file",
    "parse_xlsx_file",
    "parse_ods_file",
    "map_columns",
    "detect_identifier_field",
    "convert_value",
]
