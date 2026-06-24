# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import PGArrayField as _PGArrayField

from .field_options import FieldOptions


class PGArrayField(FieldOptions[Any], _PGArrayField): ...


__all__ = [
    "PGArrayField",
]
