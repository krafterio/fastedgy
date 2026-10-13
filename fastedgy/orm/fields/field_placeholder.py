# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import PlaceholderField as _PlaceholderField
from edgy.core.db.fields.types import BaseFieldType

from .field_options import FieldOptions


class PlaceholderField(FieldOptions[Any], _PlaceholderField):
    """A field without a column, standing for a field of ``field_type``: its pydantic type, default and metadata type."""

    def __new__(cls, field_type: Any = None, **kwargs: Any) -> Any:
        stands_for = None

        if field_type is not None:
            stands_for = field_type(null=kwargs.get("null", False))
            kwargs.setdefault("pydantic_field_type", stands_for.field_type)

            if "default" not in kwargs and stands_for.has_default():
                kwargs["default"] = stands_for.default

        obj = super().__new__(cls, **kwargs)
        obj.stands_for = stands_for

        return obj

    @classmethod
    def clean(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        field_obj: BaseFieldType,
        name: str,
        value: Any,
        for_query: bool = False,
        original_fn: Any = None,
    ) -> dict[str, Any]:
        return {}

    @classmethod
    def get_default_values(
        cls,
        field_obj: BaseFieldType,
        field_name: str,
        cleaned_data: dict[str, Any],
        original_fn: Any = None,
    ) -> dict[str, Any]:
        return {}


__all__ = [
    "PlaceholderField",
]
