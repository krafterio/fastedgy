# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Utility functions for relation operations."""

from typing import Any


class RelationOperationError(ValueError):
    """Error during relation operation processing."""

    pass


def extract_id(value: int | dict[str, Any]) -> int:
    """
    Extract ID from int or dict with 'id' field.

    Args:
        value: Either an integer ID or a dict containing an 'id' field

    Returns:
        The extracted ID

    Raises:
        RelationOperationError: If value is invalid or ID is not positive

    Examples:
        >>> extract_id(42)
        42
        >>> extract_id({"id": 42, "name": "test"})
        42
        >>> extract_id(-1)
        RelationOperationError: ID must be positive, got: -1
    """
    if isinstance(value, int):
        if value <= 0:
            raise RelationOperationError(f"ID must be positive, got: {value}")
        return value

    if isinstance(value, dict) and "id" in value:
        record_id = value["id"]
        if not isinstance(record_id, int) or record_id <= 0:
            raise RelationOperationError(
                f"ID must be a positive integer, got: {record_id}"
            )
        return record_id

    raise RelationOperationError(
        f"Invalid ID value: {value}. Expected int or dict with 'id' field."
    )


def extract_id_and_values(value: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """
    Extract ID and other values from dict (for update operation).

    Args:
        value: Dict containing 'id' field and other fields to update

    Returns:
        Tuple of (record_id, update_values)

    Raises:
        RelationOperationError: If value is invalid or missing 'id'

    Examples:
        >>> extract_id_and_values({"id": 42, "name": "New Name"})
        (42, {"name": "New Name"})
        >>> extract_id_and_values({"name": "No ID"})
        RelationOperationError: update operation requires dict with 'id' field
    """
    if not isinstance(value, dict):
        raise RelationOperationError(
            f"update operation requires dict, got: {type(value).__name__}"
        )

    if "id" not in value:
        raise RelationOperationError("update operation requires dict with 'id' field")

    data = value.copy()
    record_id = data.pop("id")

    if not isinstance(record_id, int) or record_id <= 0:
        raise RelationOperationError(f"ID must be a positive integer, got: {record_id}")

    return record_id, data
