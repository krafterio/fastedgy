# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any
from fastedgy.schemas import BaseModel


class ResequenceRequest(BaseModel):
    """
    Schema for resequencing records within a list while allowing group reassignment.

    This schema enables the reorganization of records in a list by providing
    the ability to specify a new grouping field/value and define the desired
    order of all list records through their IDs.

    Attributes:
        model_name: str: The name of the model to resequence.
        sequence_field (str | None): The field name used for sequencing records. Value must be defined to resequence.
        sequence_offset (int | None): The offset to apply to the sequence.
        group_field (str | None): The field name used for grouping records. Value must be defined to update group.
        group_value (Any | None): The new value to assign to the group field.
        ids (list[int]): List of record IDs in the desired order.
    """

    model_name: str
    sequence_field: str | None = None
    sequence_offset: int = 0
    group_field: str | None = None
    group_value: Any | None = None
    ids: list[int]


class Resequence(BaseModel):
    """
    Schema for result resequence.
    """

    model_name: str
    sequence_field: str | None = None
    sequence_offset: int = 0
    group_field: str | None = None
    group_value: Any | None = None
    records: list[dict[str, Any]]


class MetadataField(BaseModel):
    name: str
    label: str
    type: str
    readonly: bool
    required: bool
    searchable: bool
    extra: bool
    filter_operators: list[str]
    target: str | None = None
    choices: dict[str, str] | None = None


class MetadataModel(BaseModel):
    name: str
    api_name: str
    label: str
    label_plural: str
    searchable: bool
    sortable: bool
    sortable_field: str | None = None
    fields: dict[str, MetadataField]


__all__ = [
    "ResequenceRequest",
    "Resequence",
    "MetadataField",
    "MetadataModel",
]
