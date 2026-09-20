# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime
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


class SyncStateItem(BaseModel):
    """What a client needs to know to decide whether a model is up to date.

    ``count`` and ``updated_at`` are read through the model's own scoped query,
    so the workspace scope, the global filters and the row-level access rules
    apply: two accounts of the same server see their own numbers.
    """

    model: str
    mode: str
    count: int
    updated_at: datetime | None = None


class SyncState(BaseModel):
    """The state of every replicated model the caller can read."""

    items: list[SyncStateItem]


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


# Frozen: generated once and cached for the whole process, so an instance is
# shared by every workspace reading that model, and mutating one would change
# what all the others see. Said in a comment rather than a docstring, which
# would land in the OpenAPI schema as a public description.
#
# Pyright reads `frozen=True` through its dataclass rule, which forbids a frozen
# class over a non-frozen base. Pydantic has no such rule.
class MetadataField(BaseModel, frozen=True):  # pyright: ignore[reportGeneralTypeIssues]
    name: str
    label: str
    type: str
    readonly: bool
    required: bool
    searchable: bool
    extra: bool
    filter_operators: list[str]
    target: str | None = None
    targets: list[str] | None = None
    choices: dict[str, str] | None = None
    default: Any | None = None
    local_placeholder: str | None = None


# Frozen for the same reason as its fields. A read carrying the extra fields of
# a workspace gets a copy, made by `apply_workspace_extra_fields`.
class MetadataModel(BaseModel, frozen=True):  # pyright: ignore[reportGeneralTypeIssues]
    name: str
    api_name: str
    label: str
    label_plural: str
    searchable: bool
    searchable_fields: list[str]
    search_field: str | None = None
    sortable: bool
    sortable_field: str | None = None
    synchronizable: bool = False
    synchronizable_mode: str = "none"
    has_extra_fields: bool = False
    fields: dict[str, MetadataField]


__all__ = [
    "MetadataField",
    "MetadataModel",
    "Resequence",
    "ResequenceRequest",
]
