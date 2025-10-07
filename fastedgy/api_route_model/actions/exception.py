# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from pydantic_core import ErrorDetails
from sqlalchemy.exc import DBAPIError, IntegrityError

from fastedgy.i18n import _t
from fastedgy.orm.exceptions import ObjectNotFound


def handle_action_exception(
    e: Exception, model_cls: type | None = None, not_found_message: str | None = None
) -> None:
    """
    Centralized exception handler for API route model actions.

    This function handles all common exceptions that can occur during
    create, patch, delete operations and raises appropriate HTTPException
    with user-friendly messages.

    Args:
        e: The exception to handle
        model_cls: The model class (used for ObjectNotFound messages)
        not_found_message: Custom message for ObjectNotFound (optional)

    Raises:
        HTTPException: With appropriate status code and detail message
        RequestValidationError: For validation errors
        Exception: Re-raises the exception if not handled
    """
    # Handle integrity errors (constraints violations)
    if isinstance(e, IntegrityError):
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)

        # Handle unique constraint violations
        if "unique constraint" in error_msg.lower() or "UniqueViolationError" in str(
            e.orig.__class__.__name__
        ):
            # Try to extract field name from error message
            field_name = None
            if "Key (" in error_msg:
                # Extract field name from "Key (field_name)=(value) already exists"
                field_part = error_msg.split("Key (")[1].split(")")[0]
                field_name = field_part

            if field_name:
                detail = str(
                    _t(
                        "An entry with this value already exists for the field '{field_name}'.",
                        field_name=field_name,
                    )
                )
            else:
                detail = str(_t("This entry already exists in the database."))

            raise HTTPException(status_code=400, detail=detail)

        # Handle foreign key violations
        if (
            "foreign key constraint" in error_msg.lower()
            or "ForeignKeyViolationError" in str(e.orig.__class__.__name__)
        ):
            detail = str(
                _t("The reference to a related resource is invalid or does not exist.")
            )
            raise HTTPException(status_code=400, detail=detail)

        # Handle check constraint violations
        if "check constraint" in error_msg.lower() or "CheckViolationError" in str(
            e.orig.__class__.__name__
        ):
            detail = str(
                _t("The provided data does not meet the validation constraints.")
            )
            raise HTTPException(status_code=400, detail=detail)

        # Handle not null constraint violations
        if (
            "not-null constraint" in error_msg.lower()
            or "null value" in error_msg.lower()
            or "NotNullViolationError" in str(e.orig.__class__.__name__)
        ):
            detail = str(_t("A required field is missing."))
            raise HTTPException(status_code=400, detail=detail)

        # Generic integrity error
        raise HTTPException(
            status_code=400,
            detail=str(
                _t("The provided data violates a database integrity constraint.")
            ),
        )

    # Handle database API errors (serialization, etc.)
    if isinstance(e, DBAPIError):
        if "SerializationError" in str(
            e.orig.__class__.__name__
        ) or "could not serialize access" in str(e):
            raise HTTPException(
                status_code=429,
                detail=str(
                    _t(
                        "The resource is currently being used by another operation. Please try again in a few moments."
                    )
                ),
            )
        # Re-raise if not handled
        raise e

    # Handle object not found
    if isinstance(e, ObjectNotFound):
        if not_found_message:
            detail = not_found_message
        else:
            model_name = model_cls.__name__ if model_cls else "Item"
            detail = f"{model_name} not found"
        raise HTTPException(status_code=404, detail=detail)

    # Handle validation errors
    if isinstance(e, ValidationError):
        raise RequestValidationError(e.errors())

    # Handle value errors
    if isinstance(e, ValueError):
        raise RequestValidationError(
            [ErrorDetails(msg=str(e), type="value_error", loc=("body",), input=None)]
        )

    # Re-raise if not handled
    raise e


__all__ = [
    "handle_action_exception",
]
