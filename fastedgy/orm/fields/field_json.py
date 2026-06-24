# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import JSONField as _JSONField

from .field_options import FieldOptions


class JSONField(FieldOptions[Any], _JSONField): ...


__all__ = [
    "JSONField",
]
