# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum
from typing import Any, cast

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

from edgy.core.db.fields import ChoiceField as EdgyChoiceField
from edgy.core.db.fields.types import BaseFieldType


class ChoiceEnum(str, Enum):
    """
    Base class for choice enums that can be used with ChoiceField.

    Allows defining enums with translated labels:

        class UserRole(ChoiceEnum):
            admin = _ts("Administrator")
            agent = _ts("Commercial")
            user = _ts("User")
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Enum):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        """
        Custom Pydantic schema that accepts:
        - The enum member directly
        - A string matching the enum name
        - Another enum with matching name (mirror enum from DB)
        """

        def validate(value: Any) -> "ChoiceEnum":
            # If it's already a member of this enum
            if isinstance(value, cls):
                return value
            # If it's a string, look up by name
            if isinstance(value, str):
                try:
                    return cls.__members__[value]
                except KeyError:
                    raise ValueError(f"Invalid {cls.__name__}: {value}")
            # If it's another enum (mirror enum), compare by name
            if isinstance(value, Enum):
                try:
                    return cls.__members__[value.name]
                except KeyError:
                    raise ValueError(f"Invalid {cls.__name__}: {value.name}")
            raise ValueError(f"Invalid {cls.__name__}: {value}")

        def serialize(value: "ChoiceEnum") -> str:
            return value.name

        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize, info_arg=False, return_schema=core_schema.str_schema()
            ),
        )


class _ChoiceMirrorEnum(str, Enum):
    """
    Internal base class for mirror enums created by ChoiceField.
    Supports comparison with the original ChoiceEnum by name.
    """

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Enum):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name


class ChoiceField(EdgyChoiceField):
    """
    Custom ChoiceField that stores enum names (left side of =) in the database
    while preserving the enum values as labels (which can be TranslatedStrings).

    Usage with ChoiceEnum:

        class Status(ChoiceEnum):
            draft = _ts("Draft")
            published = _ts("Published")

        class MyModel(Model):
            status = ChoiceField(choices=Status)

    The database will store 'draft' and 'published' (the names),
    while the labels are available for metadata generation.

    Comparison works naturally:
        record.status == Status.draft  # True
        record.status == "draft"       # True
    """

    def __new__(cls, choices: type[Enum], **kwargs: Any) -> BaseFieldType:
        # Store the original labels mapping (name -> label value)
        kwargs["_choice_labels"] = {member.name: member.value for member in choices}

        # Create a mirror enum where value = name (for DB storage)
        # Using _ChoiceMirrorEnum as base for proper comparison support
        mirror_enum = cast(
            type[Enum],
            _ChoiceMirrorEnum(
                choices.__name__,
                {member.name: member.name for member in choices},
            ),
        )

        return super().__new__(cls, choices=mirror_enum, **kwargs)


__all__ = [
    "ChoiceEnum",
    "ChoiceField",
]
