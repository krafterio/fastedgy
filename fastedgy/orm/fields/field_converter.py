# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import abstractmethod
from typing import Any, Generic, TypeVar

from edgy.core.db.fields.types import BaseFieldType

# TypeVars for field values - input and output can be different types
InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class FieldExportConverter(Generic[InputT, OutputT]):
    """
    Mixin for field types that support export converters.

    Fields implementing this mixin can define custom converters
    that transform values during export operations.

    Example usage in a field class:

        class MyField(FieldFactory, FieldExportConverter[MyType, str]):
            @classmethod
            def get_export_converters(cls) -> list[str]:
                return ["value", "formatted"]

            @classmethod
            def export_convert(cls, field_obj, value, converter):
                if converter == "formatted":
                    return format_value(value)
                return value
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Wrap __new__ to automatically add _export_converter_class
        # This works regardless of inheritance order
        original_new = cls.__new__

        def patched_new(__cls: type, *args: Any, **kw: Any) -> Any:
            kw["_export_converter_class"] = __cls
            return original_new(__cls, *args, **kw)

        cls.__new__ = patched_new  # type: ignore

    @classmethod
    @abstractmethod
    def get_export_converters(cls) -> list[str]:
        """
        Return list of available converter names for export.

        Returns:
            List of converter name strings (e.g., ["value", "label"])
        """
        ...

    @classmethod
    @abstractmethod
    def export_convert(
        cls, field_obj: BaseFieldType, value: InputT, converter: str | None
    ) -> OutputT:
        """
        Convert value using the specified converter during export.

        Args:
            field_obj: The field instance containing metadata (e.g., _choice_labels)
            value: The value to convert (type depends on the field)
            converter: Name of the converter to apply, or None for default behavior

        Returns:
            The converted value (type defined by the implementing class)
        """
        ...


__all__ = [
    "FieldExportConverter",
]
