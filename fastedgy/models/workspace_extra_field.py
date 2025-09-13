# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum

from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin


class WorkspaceExtraFieldType(Enum):
    boolean = "boolean"
    char = "char"
    date = "date"
    datetime = "datetime"
    float = "float"
    integer = "integer"
    text = "text"


EXTRA_FIELDS_MAP = {
    WorkspaceExtraFieldType.boolean: fields.BooleanField,
    WorkspaceExtraFieldType.char: fields.CharField,
    WorkspaceExtraFieldType.date: fields.DateField,
    WorkspaceExtraFieldType.datetime: fields.DateTimeField,
    WorkspaceExtraFieldType.float: fields.FloatField,
    WorkspaceExtraFieldType.integer: fields.IntegerField,
    WorkspaceExtraFieldType.text: fields.TextField,
}

EXTRA_FIELD_TYPE_OPTIONS = {
    WorkspaceExtraFieldType.boolean: {},
    WorkspaceExtraFieldType.char: {
        "max_length": 255,
    },
    WorkspaceExtraFieldType.date: {},
    WorkspaceExtraFieldType.datetime: {},
    WorkspaceExtraFieldType.float: {},
    WorkspaceExtraFieldType.integer: {},
    WorkspaceExtraFieldType.text: {
        "max_length": 255,
    },
}


class BaseWorkspaceExtraField(BaseModel, WorkspaceableMixin):
    class Meta:
        abstract = True
        label = "Champs personnalisé"
        label_plural = "Champs personnalisés"
        unique_together = [
            ("workspace", "name"),
        ]

    label: str | None = fields.CharField(max_length=255, label="Label") # type: ignore
    name: str | None = fields.CharField(max_length=40, label="Nom technique") # type: ignore
    field_type: WorkspaceExtraFieldType | None = fields.ChoiceField(WorkspaceExtraFieldType, label="Type") # type: ignore
    required: bool = fields.BooleanField(default=False, label="Requis") # type: ignore


__all__ = [
    "WorkspaceExtraFieldType",
    "EXTRA_FIELDS_MAP",
    "EXTRA_FIELD_TYPE_OPTIONS",
    "BaseWorkspaceExtraField",
]
