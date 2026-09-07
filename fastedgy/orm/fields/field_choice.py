# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum, EnumMeta
from typing import Any, cast
from weakref import WeakKeyDictionary

from edgy.core.db.fields import ChoiceField as EdgyChoiceField
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema

from ...i18n import TranslatableString
from .field_converter import FieldExportConverter
from .field_options import FieldOptions


class ChoiceEnum(TranslatableString, Enum):
    """
    Base class for choice enums that can be used with ChoiceField.

    Allows defining enums with translated labels:

        class UserRole(ChoiceEnum):
            admin = _ts("Administrator")
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
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: GetCoreSchemaHandler) -> CoreSchema:
        """
        Custom Pydantic schema that accepts:
        - The enum member directly
        - A string matching the enum name
        - Another enum with matching name (mirror enum from DB)
        """

        def validate(value: Any) -> ChoiceEnum:
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

        def serialize(value: ChoiceEnum) -> str:
            return value.name

        return core_schema.no_info_plain_validator_function(
            validate,
            ref=f"{cls.__module__}.{cls.__qualname__}",
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize, info_arg=False, return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        member_names = [m.name for m in cls.__members__.values()]
        return {"type": "string", "enum": member_names, "title": cls.__name__}


class _ExtendableEnumMeta(EnumMeta):
    """Tells a type checker that a member may not be written in the class body.

    The members arrive at import time, from the models and from the
    application, so a static reading of the class sees almost none of them. The
    cost is that a misspelt name only fails at runtime, which is inherent to an
    enum built this way.
    """

    def __getattr__(cls, name: str) -> Any:
        raise AttributeError(name)


class ExtendableChoiceEnum(ChoiceEnum, metaclass=_ExtendableEnumMeta):
    """A choice enum that code adds members to after the class is defined.

    A model may bring one by carrying a mixin, an application by asking for it,
    and both happen at import time, long after the enum was written. The class
    object never changes, so everything that captured it keeps working: the
    pydantic annotation, the mirror enum a `ChoiceField` builds from it, and
    that field's column type.

    `_member_names_` is the order Postgres declares, which is what an
    `ORDER BY` on the column follows: `before` and `after` place a member in it.
    """

    @classmethod
    def extend(
        cls,
        name: str,
        label: "str | TranslatableString",
        *,
        before: str | None = None,
        after: str | None = None,
    ) -> Any:
        if name in cls.__members__:
            raise ValueError(f"{cls.__name__} already has a member '{name}'")

        member = _insert_member(cls, name, label, before=before, after=after)

        for mirror, field in _mirrors_of(cls):
            _insert_member(mirror, name, name, before=before, after=after)
            field._choice_labels[name] = label
            column_type = getattr(field, "column_type", None)

            if column_type is not None:
                column_type.enums = [one.name for one in mirror]

        return member

    @classmethod
    def hide(cls, name: str) -> None:
        """Stop offering a member, without taking it off the class.

        `Cls.name` still answers, so code that mentions the member keeps
        working, whether it is the framework's own or the application's. What
        goes away is the exposure: the API no longer accepts the value, the
        metadata no longer offers it, and the column type no longer holds it.

        Hide before any row uses the member: a migration that drops it from the
        Postgres type rewrites the rows that held it.
        """
        if name not in cls.__members__:
            raise ValueError(f"{cls.__name__} has no member '{name}'")

        for mirror, field in _mirrors_of(cls):
            if name not in mirror.__members__:
                continue

            _drop_member(mirror, name)
            field._choice_labels.pop(name, None)
            column_type = getattr(field, "column_type", None)

            if column_type is not None:
                column_type.enums = [one.name for one in mirror]

    @classmethod
    def restrict(cls, *names: str) -> None:
        """Offer only these members, in the order they are already declared."""
        kept = set(names)
        unknown = kept - set(cls.__members__)

        if unknown:
            raise ValueError(f"{cls.__name__} has no member {sorted(unknown)}")

        for name in [one for one in cls.__members__ if one not in kept]:
            cls.hide(name)


# Weak, so a throwaway enum and the fields built from it are collected with it.
_extended_mirrors: "WeakKeyDictionary[type[Enum], list[tuple[type[Enum], Any]]]" = WeakKeyDictionary()


def _mirrors_of(source: type[Enum]) -> "list[tuple[type[Enum], Any]]":
    return _extended_mirrors.get(source, [])


def _member_position(names: list[str], before: str | None, after: str | None) -> int:
    if before is not None and before in names:
        return names.index(before)

    if after is not None and after in names:
        return names.index(after) + 1

    return len(names)


def _drop_member(enum_cls: type[Enum], name: str) -> None:
    member = enum_cls._member_map_.pop(name)  # pyright: ignore[reportAttributeAccessIssue]
    enum_cls._member_names_.remove(name)  # pyright: ignore[reportAttributeAccessIssue]
    enum_cls._value2member_map_.pop(member.value, None)  # pyright: ignore[reportAttributeAccessIssue]
    type.__delattr__(enum_cls, name)


def _insert_member(enum_cls: type[Enum], name: str, value: Any, *, before: str | None, after: str | None) -> Any:
    member_type = enum_cls._member_type_  # pyright: ignore[reportAttributeAccessIssue]
    member = object.__new__(enum_cls) if member_type is object else member_type.__new__(enum_cls, value)
    member._name_ = name
    member._value_ = value

    names: list[str] = enum_cls._member_names_  # pyright: ignore[reportAttributeAccessIssue]
    mapping: dict[str, Any] = enum_cls._member_map_  # pyright: ignore[reportAttributeAccessIssue]

    mapping[name] = member
    enum_cls._value2member_map_.setdefault(value, member)  # pyright: ignore[reportAttributeAccessIssue]
    names.insert(_member_position(names, before, after), name)

    # `__members__` reads the mapping, iteration reads the names: reordered
    # together, or a member placed by `before` would show up in one order and
    # be declared to Postgres in another.
    ordered = {one: mapping[one] for one in names if one in mapping}
    ordered.update({one: member for one, member in mapping.items() if one not in ordered})
    mapping.clear()
    mapping.update(ordered)

    type.__setattr__(enum_cls, name, member)

    return member


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

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: GetCoreSchemaHandler) -> CoreSchema:
        """
        Custom Pydantic schema that always serializes to the member name and
        accepts the mirror member, the original ChoiceEnum (by name) or a string.

        Without this, Pydantic builds a default enum schema for the mirror enum;
        when the stored value is the original ChoiceEnum (whose value is a
        TranslatableString), serialization emits a warning and the translated
        label instead of the name.
        """

        def validate(value: Any) -> _ChoiceMirrorEnum:
            if isinstance(value, cls):
                return value
            if isinstance(value, str):
                try:
                    return cls.__members__[value]
                except KeyError:
                    raise ValueError(f"Invalid {cls.__name__}: {value}")
            if isinstance(value, Enum):
                try:
                    return cls.__members__[value.name]
                except KeyError:
                    raise ValueError(f"Invalid {cls.__name__}: {value.name}")
            raise ValueError(f"Invalid {cls.__name__}: {value}")

        def serialize(value: Any) -> str:
            return value.name if isinstance(value, Enum) else str(value)

        return core_schema.no_info_plain_validator_function(
            validate,
            ref=f"{cls.__module__}.{cls.__qualname__}",
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize, info_arg=False, return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, _core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        member_names = [m.name for m in cls.__members__.values()]
        return {"type": "string", "enum": member_names, "title": cls.__name__}


class ChoiceField(FieldOptions[Any], EdgyChoiceField, FieldExportConverter[Enum | None, str | None]):
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

    Export converters:
        - "value": Returns the enum name (e.g., "draft")
        - "label": Returns the translated label (e.g., "Draft")
    """

    _choice_labels: dict[str, str | TranslatableString]

    def __new__[E: Enum](cls, choices: type[E], **kwargs: Any) -> E:
        # Create a mirror enum where value = name (for DB storage)
        # Using _ChoiceMirrorEnum as base for proper comparison support
        mirror_enum = cast(
            type[Enum],
            _ChoiceMirrorEnum(
                choices.__name__,
                {member.name: member.name for member in choices},
            ),
        )

        label = kwargs.get("label")
        if label is not None and "title" not in kwargs:
            kwargs["title"] = label.message if isinstance(label, TranslatableString) else str(label)

        obj = super().__new__(cls, choices=mirror_enum, **kwargs)
        cast("ChoiceField", obj)._choice_labels = {member.name: member.value for member in choices}

        if isinstance(choices, type) and issubclass(choices, ExtendableChoiceEnum):
            # An enum still empty at this point gives SQLAlchemy nothing to name
            # the Postgres type after, and it is the normal case here: the
            # members arrive with the models, which are imported later.
            column_type = getattr(obj, "column_type", None)

            if column_type is not None and not getattr(column_type, "name", None):
                column_type.name = mirror_enum.__name__.lower()

            _extended_mirrors.setdefault(choices, []).append((mirror_enum, obj))

        return obj

    @property
    def choice_labels(self) -> dict[str, str | TranslatableString]:
        return self._choice_labels

    def get_export_converters(self) -> list[str]:
        return ["value", "label"]

    def export_convert(self, value: Enum | None, converter: str | None) -> str | None:
        if value is None:
            return None

        name = value.name if isinstance(value, Enum) else str(value)

        if converter == "label":
            # Use _choice_labels directly because Edgy's factory pattern
            # doesn't preserve our property, only the stored attribute
            return str(self._choice_labels.get(name, name))

        return name


__all__ = [
    "ChoiceEnum",
    "ChoiceField",
    "ExtendableChoiceEnum",
]
