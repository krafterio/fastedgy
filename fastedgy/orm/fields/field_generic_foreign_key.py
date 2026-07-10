# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Sequence, cast

import sqlalchemy

from edgy.core.db.fields.base import BaseField
from edgy.core.db.fields.types import BaseFieldType

from fastedgy.orm.access_guard import AccessDeniedError

from .field_char import CharField
from .field_integer import IntegerField


GenericTargets = Callable[[], Iterable[Any]] | Iterable[Any]


def generic_target_name(model_cls: type) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", model_cls.__name__).lower()


def resolve_generic_pair(model_cls: Any, field_path: str) -> tuple[Any, str] | None:
    """Resolve a virtual pair path on a GenericForeignKey: ``<field>.$model``
    (the target model name column) or ``<field>.id`` (the target id column).
    Returns ``(field, "model" | "id")`` or None when the path is not one."""
    parts = field_path.split(".")
    if len(parts) != 2 or parts[1] not in ("$model", "id"):
        return None

    fields = getattr(getattr(model_cls, "meta", None), "fields", None)
    field = fields.get(parts[0]) if fields else None
    if not getattr(field, "is_generic_foreign_key", False):
        return None

    return field, "model" if parts[1] == "$model" else "id"


def resolve_registry_generic_references(model_cls: Any) -> None:
    """Resolve every GenericForeignKey of the model's Edgy registry so the
    reverse relations are installed on their targets. Input model generators
    call it before building (their result is cached): an input generated ahead
    of the resolution would silently drop the relation's payload key."""
    registry = getattr(getattr(model_cls, "meta", None), "registry", None)
    models = getattr(registry, "models", None)
    if not models:
        return

    for model in list(models.values()):
        fields = getattr(getattr(model, "meta", None), "fields", None) or {}
        for field in fields.values():
            if getattr(field, "is_generic_foreign_key", False):
                try:
                    cast(Any, field).targets()
                except ValueError:
                    continue


def validate_generic_reference_payload(model_cls: Any, data: dict[str, Any], partial: bool = False) -> None:
    """Cross-validate the generic reference forms of an input payload: the
    reference object and the exposed column pair are exclusive, columns always
    come as a full pair (both set, or both null when the relation is nullable)
    pointing to an allowed target, and a non-nullable relation must be provided
    on create through one of the two forms."""
    from fastapi import HTTPException

    fields = getattr(getattr(model_cls, "meta", None), "fields", None)
    if not fields:
        return

    for field in list(fields.values()):
        if not getattr(field, "is_generic_foreign_key", False):
            continue

        reference_in = field.name in data
        model_in = field.model_column in data
        id_in = field.id_column in data

        if reference_in and (model_in or id_in):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{field.name}' accepts either the reference object or the "
                    f"'{field.model_column}'/'{field.id_column}' pair, not both"
                ),
            )

        if model_in != id_in:
            raise HTTPException(
                status_code=422,
                detail=f"'{field.model_column}' and '{field.id_column}' must be provided together",
            )

        if model_in:
            model_value = data[field.model_column]
            id_value = data[field.id_column]

            if (model_value is None) != (id_value is None):
                raise HTTPException(
                    status_code=422,
                    detail=f"'{field.model_column}' and '{field.id_column}' must be both set or both null",
                )

            if model_value is None:
                if not field.relation_nullable:
                    raise HTTPException(status_code=422, detail=f"'{field.name}' is required")
            elif model_value not in field.targets():
                raise HTTPException(
                    status_code=422,
                    detail=f"'{field.name}': model '{model_value}' is not an allowed target",
                )
        elif reference_in:
            if data[field.name] is None and not field.relation_nullable:
                raise HTTPException(status_code=422, detail=f"'{field.name}' is required")
        elif not partial and not field.relation_nullable:
            raise HTTPException(status_code=422, detail=f"'{field.name}' is required")


class GenericRelation:
    """Runtime accessor of a generic reverse relation: a filtered queryset over
    the owning model plus ``add``/``remove`` helpers. Unknown attributes are
    delegated to the queryset (``all``, ``filter``, ``count``, ``limit``, ...)."""

    def __init__(self, instance: Any, field: "GenericRelatedField") -> None:
        self.__dict__["instance"] = instance
        self.__dict__["field"] = field

    def _link_values(self) -> dict[str, Any]:
        generic_field = self.field.generic_field
        return {
            generic_field.model_column: generic_target_name(type(self.instance)),
            generic_field.id_column: getattr(self.instance, "id", None),
        }

    @property
    def queryset(self) -> Any:
        return self.field.related_from.query.filter(**self._link_values())

    def __getattr__(self, item: str) -> Any:
        return getattr(self.queryset, item)

    async def add(self, child: Any) -> Any:
        for column_name, column_value in self._link_values().items():
            setattr(child, column_name, column_value)
        await child.save()
        return child

    async def remove(self, child: Any) -> Any:
        from fastedgy.orm.relations.utils import RelationOperationError

        generic_field = self.field.generic_field
        if not generic_field.relation_nullable:
            raise RelationOperationError(f"Generic reference '{generic_field.name}' is required and cannot be unlinked")

        setattr(child, generic_field.model_column, None)
        setattr(child, generic_field.id_column, None)
        await child.save()
        return child


class GenericRelatedField(BaseField):
    """Reverse side of a GenericForeignKey, installed on each target model under
    the ``related_name``: a virtual to-many field (no columns) resolving to the
    owning model rows whose generic columns point back to the instance."""

    is_generic_related = True

    def __init__(self, *, generic_field_name: str, related_from: type, **kwargs: Any) -> None:
        self.generic_field_name = generic_field_name
        self.related_from = related_from

        kwargs.setdefault("exclude", True)
        kwargs.setdefault("filterable", True)
        kwargs.setdefault("searchable", False)
        kwargs["null"] = True
        kwargs["primary_key"] = False
        kwargs["field_type"] = kwargs["annotation"] = Any
        super().__init__(**kwargs)

    @property
    def generic_field(self) -> "GenericForeignKey":
        return cast("GenericForeignKey", self.related_from.meta.fields[self.generic_field_name])

    def get_columns(self, name: str) -> Sequence[sqlalchemy.Column]:
        return []

    def to_model(self, field_name: str, value: Any) -> dict[str, Any]:
        return {}

    def clean(self, field_name: str, value: Any, for_query: bool = False) -> dict[str, Any]:
        return {}

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        if instance is None:
            return self
        return GenericRelation(instance, self)


class GenericForeignKey(BaseField):
    """
    Polymorphic many-to-one relation stored as two sibling columns injected on
    the owner model: ``<name>_model`` (target metadata name) and ``<name>_id``
    (target primary key). Column names are overridable with ``model_column`` /
    ``id_column`` so existing schemas can adopt the field without renaming.

    ``to`` restricts the allowed targets: an iterable of model classes or class
    names, or a callable returning one (resolved lazily, so it can be backed by
    an application registry filled at import time).

    Reading is asynchronous and cached per instance: ``await item.record``.
    Writing accepts a target instance, a ``{"model": ..., "id": ...}`` mapping
    or ``None``; both sibling columns stay directly addressable and filterable.

    Target records load through ``target_cls.query``, so global filters and
    access guards fully apply: a target the current context is denied to read
    resolves to ``None`` instead of propagating the denial.

    ``expose_columns`` keeps the sibling columns on the API surface for
    backward compatibility: ``"none"`` (default) hides them entirely,
    ``"read"`` serializes and filters them but rejects writes, ``"write"``
    additionally accepts them in input payloads — always as a full pair
    (both set, or both null when the relation is nullable), exclusive with
    the reference object, and validated against the allowed targets.

    Usage:
        class Reminder(BaseModel):
            record = fields.GenericForeignKey(
                to=["Task", "CalendarEvent"],
                model_column="model_name",
                id_column="record_id",
            )
    """

    is_generic_foreign_key = True

    def __init__(
        self,
        to: GenericTargets,
        *,
        related_name: str | None = None,
        model_column: str | None = None,
        id_column: str | None = None,
        model_field_kwargs: dict[str, Any] | None = None,
        id_field_kwargs: dict[str, Any] | None = None,
        expose_columns: str = "none",
        **kwargs: Any,
    ) -> None:
        if expose_columns not in ("none", "read", "write"):
            raise ValueError(f"GenericForeignKey: invalid expose_columns '{expose_columns}'")

        self.to = to
        self.related_name = related_name
        self.expose_columns = expose_columns
        self._model_column_option = model_column
        self._id_column_option = id_column
        self._model_field_kwargs = model_field_kwargs or {}
        self._id_field_kwargs = id_field_kwargs or {}
        self._targets_cache: dict[str, type] | None = None
        self.relation_nullable = bool(kwargs.get("null", False))

        kwargs.setdefault("exclude", True)
        kwargs.setdefault("filterable", True)
        kwargs.setdefault("searchable", False)
        kwargs["null"] = True
        kwargs["primary_key"] = False
        kwargs["field_type"] = kwargs["annotation"] = Any
        super().__init__(**kwargs)

    @property
    def model_column(self) -> str:
        return self._model_column_option or f"{self.name}_model"

    @property
    def id_column(self) -> str:
        return self._id_column_option or f"{self.name}_id"

    def targets(self) -> dict[str, type]:
        if self._targets_cache is not None and not callable(self.to):
            return self._targets_cache

        source = self.to() if callable(self.to) else self.to
        resolved: dict[str, type] = {}

        for target in source:
            model_cls = self._resolve_target_class(target)
            resolved[generic_target_name(model_cls)] = model_cls

        if not resolved:
            raise ValueError(f"GenericForeignKey '{self.name}' resolved no target model")

        # A callable source is a living registry: never freeze it, so targets
        # registered after the first resolution still join the relation.
        if self._targets_cache is None or set(resolved) != set(self._targets_cache):
            self._install_inverse_relations(resolved)

        self._targets_cache = resolved
        return resolved

    def _install_inverse_relations(self, targets: dict[str, type]) -> None:
        if not self.related_name or self.owner is None:
            return

        for target_cls in targets.values():
            existing = target_cls.meta.fields.get(self.related_name)
            if existing is not None:
                if getattr(existing, "is_generic_related", False):
                    continue
                raise ValueError(
                    f"GenericForeignKey '{self.name}': related_name '{self.related_name}' "
                    f"collides with an existing field on {target_cls.__name__}"
                )

            inverse = GenericRelatedField(generic_field_name=self.name, related_from=self.owner)
            inverse.name = self.related_name
            inverse.owner = target_cls
            target_cls.meta.fields[self.related_name] = inverse

            pydantic_fields = getattr(target_cls, "__pydantic_fields__", None)
            if pydantic_fields is not None and self.related_name not in pydantic_fields:
                pydantic_fields[self.related_name] = inverse
                target_cls.model_rebuild(force=True)

    def _resolve_target_class(self, target: Any) -> type:
        if isinstance(target, str):
            registry: Any = self.owner.meta.registry if self.owner is not None else None
            models = getattr(registry, "models", None)
            if not models or target not in models:
                raise ValueError(f"GenericForeignKey '{self.name}': unknown target model '{target}'")
            return models[target]
        return target

    def get_embedded_fields(self, field_name: str, fields: dict[str, BaseFieldType]) -> dict[str, BaseFieldType]:
        model_column = self._model_column_option or f"{field_name}_model"
        id_column = self._id_column_option or f"{field_name}_id"

        embedded: dict[str, BaseFieldType] = {}
        specs = (
            (model_column, CharField, {"max_length": 100, **self._model_field_kwargs}),
            (id_column, IntegerField, dict(self._id_field_kwargs)),
        )

        for column_name, factory, extra_kwargs in specs:
            existing = fields.get(column_name)
            if existing is not None and existing.owner is None:
                raise ValueError(
                    f"GenericForeignKey '{field_name}': column field '{column_name}' is already declared on the model"
                )

            extra_kwargs.setdefault("null", self.relation_nullable)
            extra_kwargs.setdefault("searchable", False)
            # Storage detail by default: hidden from schemas, inputs, metadata
            # and public filters — the generic field is the API surface
            # (`<name>.$model` / `<name>.id` paths, reference values). The
            # expose_columns option keeps them public for backward compat;
            # override per column through model_field_kwargs / id_field_kwargs.
            if self.expose_columns == "none":
                extra_kwargs.setdefault("exclude", True)
                extra_kwargs.setdefault("filterable", False)
            else:
                extra_kwargs.setdefault("exclude", False)
                extra_kwargs.setdefault("filterable", True)
                if self.expose_columns == "read":
                    extra_kwargs.setdefault("read_only", True)
            sub_field = cast(Any, factory(**extra_kwargs))
            sub_field.owner = self.owner
            sub_field.inherit = False
            sub_field.is_generic_column = True
            sub_field.annotation = (None | sub_field.field_type) if sub_field.null else sub_field.field_type
            embedded[column_name] = sub_field

        return embedded

    def get_columns(self, name: str) -> Sequence[sqlalchemy.Column]:
        return []

    def to_model(self, field_name: str, value: Any) -> dict[str, Any]:
        return self._decompose(value)

    def clean(self, field_name: str, value: Any, for_query: bool = False) -> dict[str, Any]:
        return self._decompose(value)

    def _decompose(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {self.model_column: None, self.id_column: None}

        if isinstance(value, dict):
            model_name = value.get("model")
            record_id = value.get("id")
            if not model_name or record_id is None:
                raise ValueError(
                    f"GenericForeignKey '{self.name}': mapping value requires 'model' and 'id' keys, got {value!r}"
                )
            if model_name not in self.targets():
                raise ValueError(f"GenericForeignKey '{self.name}': model '{model_name}' is not an allowed target")
            return {self.model_column: model_name, self.id_column: record_id}

        value_cls = type(value)
        model_name = generic_target_name(value_cls)
        target_cls = self.targets().get(model_name)
        if target_cls is None or not isinstance(value, target_cls):
            if hasattr(value, "model_dump"):
                return self._decompose(value.model_dump())
            raise ValueError(f"GenericForeignKey '{self.name}': {value_cls.__name__} is not an allowed target")

        record_id = getattr(value, "id", None)
        if record_id is None:
            raise ValueError(f"GenericForeignKey '{self.name}': target instance must be saved before assignment")

        return {self.model_column: model_name, self.id_column: record_id}

    def _cache_key(self) -> str:
        return f"_gfk_cache_{self.name}"

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        if instance is None:
            return self
        return self._aload(instance)

    async def _aload(self, instance: Any) -> Any:
        cache_key = self._cache_key()
        if cache_key in instance.__dict__:
            return instance.__dict__[cache_key]

        model_name = instance.__dict__.get(self.model_column)
        record_id = instance.__dict__.get(self.id_column)

        if not model_name or record_id is None:
            return None

        target_cls = self.targets().get(model_name)
        if target_cls is None:
            return None

        try:
            record = await target_cls.query.get_or_none(pk=record_id)
        except AccessDeniedError:
            record = None

        instance.__dict__[cache_key] = record
        return record

    def __set__(self, instance: Any, value: Any) -> None:
        values = self._decompose(value)
        for column_name, column_value in values.items():
            setattr(instance, column_name, column_value)

        cache_key = self._cache_key()
        if value is None or not isinstance(value, dict):
            instance.__dict__[cache_key] = value
        else:
            instance.__dict__.pop(cache_key, None)


__all__ = [
    "GenericForeignKey",
    "GenericRelatedField",
    "GenericRelation",
    "GenericTargets",
    "generic_target_name",
    "resolve_generic_pair",
    "resolve_registry_generic_references",
    "validate_generic_reference_payload",
]
