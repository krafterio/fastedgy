# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import ForeignKey as _ForeignKey

from .field_options import FieldOptions


class ForeignKey(FieldOptions[Any], _ForeignKey): ...


__all__ = [
    "ForeignKey",
]
