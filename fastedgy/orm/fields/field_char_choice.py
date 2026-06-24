# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum
from typing import Any

from edgy.core.db.fields import CharChoiceField as _CharChoiceField

from .field_options import FieldOptions


class CharChoiceField(FieldOptions[Any], _CharChoiceField):
    def __new__[E: Enum](cls, choices: type[E], **kwargs: Any) -> E:
        return super().__new__(cls, choices=choices, **kwargs)


__all__ = [
    "CharChoiceField",
]
