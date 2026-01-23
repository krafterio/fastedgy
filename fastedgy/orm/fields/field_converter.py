# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import abstractmethod
from typing import Any, Generic, TypeVar

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
            def get_export_converters(self) -> list[str]:
                return ["value", "formatted"]

            def export_convert(self, value, converter):
                if converter == "formatted":
                    return format_value(value)
                return value

    Note: Due to Edgy's factory pattern, we store _export_converter_class
    in kwargs to preserve the original class reference for export operations.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Wrap __new__ to automatically add _export_converter_class
        # This is needed because Edgy creates a new class dynamically
        # and the original methods are not inherited
        original_new = cls.__new__

        def patched_new(__cls: type, *args: Any, **kw: Any) -> Any:
            kw["_export_converter_class"] = __cls
            return original_new(__cls, *args, **kw)

        cls.__new__ = patched_new  # type: ignore

    @abstractmethod
    def get_export_converters(self) -> list[str]:
        """
        Return list of available converter names for export.

        Returns:
            List of converter name strings (e.g., ["value", "label"])
        """
        ...

    @abstractmethod
    def export_convert(self, value: InputT, converter: str | None) -> OutputT:
        """
        Convert value using the specified converter during export.

        Args:
            value: The value to convert (type depends on the field)
            converter: Name of the converter to apply, or None for default behavior

        Returns:
            The converted value (type defined by the implementing class)
        """
        ...


__all__ = [
    "FieldExportConverter",
]
