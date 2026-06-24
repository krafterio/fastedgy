# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields import CharChoiceField as _CharChoiceField

from .field_options import FieldOptions


class CharChoiceField(FieldOptions[str], _CharChoiceField): ...


__all__ = [
    "CharChoiceField",
]
