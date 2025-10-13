# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Pydantic models for relation operations (tuple-based API)."""

from typing import Literal, Any, Annotated, Union
from pydantic import BaseModel, Field, RootModel, field_validator


# Helper types for ID representation
IdOrObject = Union[int, dict[str, Any]]  # Accept 42 or {"id": 42, ...}


class CreateOp(RootModel):
    """
    ["create", {...}] - Create a new record and link it.

    Example:
        ["create", {"name": "Supermarché", "code": "SM"}]
    """

    root: tuple[Literal["create"], dict[str, Any]]

    model_config = {
        "json_schema_extra": {
            "description": "Create a new related record and link it",
            "examples": [["create", {"name": "Supermarché", "code": "SM"}]],
        }
    }


class UpdateOp(RootModel):
    """
    ["update", {"id": ..., ...}] - Update a record (id required in object).

    Example:
        ["update", {"id": 23, "name": "Hypermarché"}]
    """

    root: tuple[Literal["update"], dict[str, Any]]

    @field_validator("root")
    @classmethod
    def validate_id_present(cls, v):
        action, data = v
        if not isinstance(data, dict) or "id" not in data:
            raise ValueError("update operation requires an object with 'id' field")
        if not isinstance(data["id"], int) or data["id"] <= 0:
            raise ValueError("id must be a positive integer")
        return v

    model_config = {
        "json_schema_extra": {
            "description": "Update an existing record and ensure it's linked",
            "examples": [["update", {"id": 23, "name": "Hypermarché"}]],
        }
    }


class DeleteOp(RootModel):
    """
    ["delete", 42] or ["delete", {"id": 42}] - Delete a record.

    Examples:
        ["delete", 42]
        ["delete", {"id": 42}]
    """

    root: tuple[Literal["delete"], IdOrObject]

    model_config = {
        "json_schema_extra": {
            "description": "Delete the related record (removes relation automatically)",
            "examples": [["delete", 42], ["delete", {"id": 42}]],
        }
    }


class UnlinkOp(RootModel):
    """
    ["unlink", 42] or ["unlink", {"id": 42}] - Remove relation without deleting.

    Examples:
        ["unlink", 52]
        ["unlink", {"id": 52}]
    """

    root: tuple[Literal["unlink"], IdOrObject]

    model_config = {
        "json_schema_extra": {
            "description": "Remove relation without deleting the record",
            "examples": [["unlink", 52], ["unlink", {"id": 52}]],
        }
    }


class LinkOp(RootModel):
    """
    ["link", 42] or ["link", {"id": 42}] - Add relation to existing record.

    Examples:
        ["link", 74]
        ["link", {"id": 74}]
    """

    root: tuple[Literal["link"], IdOrObject]

    model_config = {
        "json_schema_extra": {
            "description": "Link an existing record (without modifying it)",
            "examples": [["link", 74], ["link", {"id": 74}]],
        }
    }


class SetOp(RootModel):
    """
    ["set", [1, 2, 3]] - Replace all relations with given IDs.

    Example:
        ["set", [1, 2, 3]]
    """

    root: tuple[Literal["set"], list[int]]

    model_config = {
        "json_schema_extra": {
            "description": "Replace all relations with the given IDs (unlink others, link new ones)",
            "examples": [["set", [1, 2, 3]]],
        }
    }


class ClearOp(RootModel):
    """
    ["clear"] - Remove all relations.

    Example:
        ["clear"]
    """

    root: tuple[Literal["clear"]]

    model_config = {
        "json_schema_extra": {
            "description": "Remove all relations (unlink all)",
            "examples": [["clear"]],
        }
    }


# Union of all operation types
# Note: No discriminator on tuples - Pydantic will validate each variant
RelationOperation = CreateOp | UpdateOp | DeleteOp | UnlinkOp | LinkOp | SetOp | ClearOp
