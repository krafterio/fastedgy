# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from uuid import UUID

from edgy.core.db.fields import UUIDField as _UUIDField

from .field_options import FieldOptions


class UUIDField(FieldOptions[UUID], _UUIDField): ...


__all__ = [
    "UUIDField",
]
