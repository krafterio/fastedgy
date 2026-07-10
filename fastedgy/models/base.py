# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n import _ts

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Self

from datetime import datetime

from fastedgy.orm import Model, Meta, fields
from fastedgy.orm.manager import (
    BaseManager,
    Manager,
    AccessControlManager,
    AccessControlRedirectManager,
)
from fastedgy.orm.view import create_view
from fastedgy.orm.registry import lazy_register_model
from fastedgy.schemas import ConfigDict

from edgy.core.db.models.metaclasses import BaseModelMeta

from sqlalchemy import MetaData, Selectable, Table


def _optimize_edgy_field_extraction() -> None:
    """Make Edgy's field/manager extraction visit each class only once.

    Upstream ``extract_fields_and_managers`` recurses ``base.__mro__[1:]`` for
    every base and, for meta-less classes, calls ``inspect.getmembers(base)``
    (which itself walks the whole MRO). With several mixins sharing ancestors
    the same classes get rescanned O(MRO²) times — tens of thousands of
    ``getmembers`` calls across a real model set, about half of model-import
    (and therefore CLI/app startup) time.

    This drop-in replacement threads a ``seen`` set through the recursion so
    each class is processed once. It does not change *what* is extracted:
    under the upstream "first occurrence wins" rule the skipped revisits were
    already no-ops, so the resulting attrs (and their order) are identical.
    """
    import inspect
    from edgy.core.db.models import metaclasses as _mc

    if getattr(_mc.extract_fields_and_managers, "_fastedgy_optimized", False):
        return

    base_field_type = getattr(_mc, "BaseFieldType")
    base_manager = getattr(_mc, "BaseManager")
    base_model_meta = _mc.BaseModelMeta
    occluded = _mc._occluded_sentinel

    def _extract(base: type, attrs: dict, seen: set) -> None:
        if base in seen:
            return
        seen.add(base)

        from edgy.core.db.fields.composite_field import CompositeField

        meta = getattr(base, "meta", None)
        if not meta:
            for key, value in inspect.getmembers(base):
                if key not in attrs:
                    if isinstance(value, base_field_type):
                        attrs[key] = value
                    elif isinstance(value, base_manager):
                        attrs[key] = value.__class__()
                    elif isinstance(value, base_model_meta):
                        attrs[key] = CompositeField(
                            inner_fields=value,
                            prefix_embedded=f"{key}_",
                            inherit=value.meta.inherit,
                            name=key,
                            owner=value,
                        )
                elif attrs[key] is occluded:
                    if isinstance(value, base_field_type) and value.inherit:
                        attrs[key] = value
                    elif isinstance(value, base_manager) and value.inherit:
                        attrs[key] = value.__class__()
                    elif isinstance(value, base_model_meta) and value.meta.inherit:
                        attrs[key] = CompositeField(
                            inner_fields=value,
                            prefix_embedded=f"{key}_",
                            inherit=value.meta.inherit,
                            name=key,
                            owner=value,
                        )
        else:
            for key, value in meta.fields.items():
                if key not in attrs:
                    if meta.abstract or value.inherit:
                        attrs[key] = value
                        assert value.owner is not None
                    else:
                        attrs[key] = occluded
                elif attrs[key] is occluded and value.inherit:
                    attrs[key] = value
                    assert value.owner is not None
            for key, value in meta.managers.items():
                if key not in attrs:
                    if meta.abstract or value.inherit:
                        attrs[key] = value
                    else:
                        attrs[key] = occluded
                elif attrs[key] is occluded and value.inherit:
                    attrs[key] = value

        for parent in base.__mro__[1:]:
            _extract(parent, attrs, seen)

    def extract_fields_and_managers(bases, attrs=None):
        from edgy.core.db.fields.composite_field import CompositeField

        attrs = {} if attrs is None else {**attrs}
        for key in list(attrs.keys()):
            value = attrs[key]
            if isinstance(value, base_model_meta):
                attrs[key] = CompositeField(
                    inner_fields=value,
                    prefix_embedded=f"{key}_",
                    inherit=value.meta.inherit,
                    owner=value,
                )
        seen: set[type] = set()
        for base in bases:
            _extract(base, attrs, seen)
        for key in list(attrs.keys()):
            if attrs[key] is occluded:
                attrs.pop(key)
        return attrs

    extract_fields_and_managers._fastedgy_optimized = True  # type: ignore[attr-defined]
    _mc.extract_fields_and_managers = extract_fields_and_managers


_optimize_edgy_field_extraction()


class ModelMeta(BaseModelMeta):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any], **kwargs: Any) -> type:
        _fix_meta_abstract_before_build(attrs)
        new_class = super().__new__(mcs, name, bases, attrs, **kwargs)
        _rebuild_for_embedded_fields(new_class)
        return new_class

    if TYPE_CHECKING:

        def __hash__(self) -> int: ...


def _rebuild_for_embedded_fields(cls: type) -> None:
    """Fields injected through ``get_embedded_fields`` (e.g. the columns of a
    ``GenericForeignKey``) miss the annotation pass run for class-namespace
    fields, so the pydantic-core schema compiled during the build treats them
    as non-nullable. Their ``FieldInfo.annotation`` is correct by the end of
    the build — one forced rebuild realigns the compiled validator."""
    meta = getattr(cls, "meta", None)
    fields = getattr(meta, "fields", None)
    if not fields:
        return

    generic_fields = [field for field in fields.values() if getattr(field, "is_generic_foreign_key", False)]
    if not generic_fields:
        return

    cls.model_rebuild(force=True)

    for field in generic_fields:
        try:
            field.targets()
        except ValueError:
            continue


def _fix_meta_abstract_before_build(attrs: dict[str, Any]) -> None:
    """A ``Meta`` extending ``BaseModel.Meta`` silently inherits ``abstract = True``,
    which makes Edgy's metaclass skip its whole non-abstract block (implicit pk,
    ``get_embedded_fields`` injection) before ``_fix_inherited_abstract`` can flip
    the flag back. When the class declares its own fields and did not explicitly
    opt into abstract, correct the flag before the build so the native path runs."""
    from edgy.core.db.fields.types import BaseFieldType

    meta_class = attrs.get("Meta")
    if (
        meta_class is None
        or not isinstance(meta_class, type)
        or "abstract" in meta_class.__dict__
        or not getattr(meta_class, "abstract", False)
    ):
        return

    if any(isinstance(value, BaseFieldType) for value in attrs.values()):
        meta_class.abstract = False


def _fix_inherited_abstract(cls: type) -> None:
    """Edgy's metaclass detects ``abstract`` via ``getattr(meta_class, "abstract", False)``
    which traverses the MRO. Subclasses that extend ``BaseModel.Meta`` or
    ``BaseView.Meta`` therefore silently inherit ``abstract = True`` and are
    excluded from registration. Reset it for concrete subclasses that have
    their own fields but did not explicitly opt into abstract.

    The metaclass also skips its whole non-abstract block for these classes,
    so the two side effects it would have produced are replayed here: the
    implicit ``pk`` field and the fields contributed by ``get_embedded_fields``
    (e.g. the columns of a ``GenericForeignKey``).
    """
    own_meta = cls.__dict__.get("Meta")
    if (
        own_meta is None
        or not isinstance(own_meta, type)
        or "abstract" in own_meta.__dict__
        or not getattr(cls, "meta", None)
        or not cls.meta.abstract
        or not cls.meta.fields
    ):
        return

    cls.meta.abstract = False

    model_fields_on_class = getattr(cls, "__pydantic_fields__", None)
    if model_fields_on_class is None:
        model_fields_on_class = getattr(cls, "model_fields", None)

    if "pk" not in cls.meta.fields:
        from edgy.core.db.fields.base import PKField

        pk_field = PKField(exclude=True, name="pk", inherit=False, no_copy=True)
        pk_field.owner = cls
        cls.meta.fields["pk"] = pk_field
        if model_fields_on_class is not None:
            model_fields_on_class["pk"] = pk_field

    for field_name, field in list(cls.meta.fields.items()):
        embedded_fields = field.get_embedded_fields(field_name, cls.meta.fields)
        if not embedded_fields:
            continue
        for sub_field_name, sub_field in embedded_fields.items():
            if sub_field_name == "pk" or sub_field_name in cls.meta.fields:
                continue
            sub_field.name = sub_field_name
            sub_field.owner = cls
            cls.meta.fields[sub_field_name] = sub_field
            if model_fields_on_class is not None:
                model_fields_on_class[sub_field_name] = sub_field


_PARTIAL_OBJECT: dict[str, Any] = {"type": "object", "additionalProperties": True}


# Local copies of api_route_model.action.relations, inlined so the schema hooks
# can run at model-build time without importing that package (which imports back
# into models.base, a circular import).
def _is_foreign_key_field(field: Any) -> bool:
    from edgy.core.db.fields.foreign_keys import ForeignKey

    return isinstance(field, ForeignKey)


def _is_exposed_relation_field(field: Any) -> bool:
    from edgy.core.db.relationships.related_field import RelatedField

    is_m2m = getattr(field, "is_m2m", False) is True
    if not (is_m2m or isinstance(field, RelatedField)):
        return False

    if is_m2m:
        return True

    related_name = getattr(field, "related_name", None) or getattr(field, "name", None)
    if not related_name or related_name == "+":
        return False

    return not related_name.endswith("_set")


def _related_model_name(field: Any) -> str | None:
    """The ``__name__`` of the model on the other side of a relation (FK / O2M / M2M).

    A reverse M2M's ``related_from`` is the auto-generated junction model, not the
    target, so it is resolved through the junction's other foreign key."""
    from edgy.core.db.relationships.related_field import RelatedField

    if not isinstance(field, RelatedField):
        target = getattr(field, "target", None)
        return getattr(target, "__name__", None)

    related_from = field.related_from
    multi_related = getattr(getattr(related_from, "meta", None), "multi_related", None)

    if multi_related:
        fk_name = getattr(field, "foreign_key_name", None)
        target_fk = next((name for name in next(iter(multi_related)) if name != fk_name), None)
        fields = getattr(related_from, "model_fields", {})
        target = getattr(fields.get(target_fk), "target", None) if target_fk else None
        return getattr(target, "__name__", None)

    return getattr(related_from, "__name__", None)


def _target_ref(field: Any) -> dict[str, Any]:
    """A ``$ref`` to the related model's schema, or a bare object when it is unknown."""
    name = _related_model_name(field)
    return {"$ref": f"#/components/schemas/{name}"} if name else dict(_PARTIAL_OBJECT)


def _foreign_key_json_schema(prop: dict[str, Any], target_ref: dict[str, Any], nullable: bool) -> dict[str, Any]:
    """A foreign key renders as ``related model | object`` — the full related model
    or a partial ``{...}`` from an X-Fields selection — plus ``null`` when nullable.
    Built explicitly (not from the model's own rendering, which degrades to ``any``
    for a cyclic relation)."""
    variants: list[dict[str, Any]] = [target_ref, dict(_PARTIAL_OBJECT)]
    if nullable:
        variants.append({"type": "null"})

    result: dict[str, Any] = {"anyOf": variants}
    for key in ("title", "default"):
        if key in prop:
            result[key] = prop[key]
    return result


def _relation_json_schema(title: str, target_ref: dict[str, Any]) -> dict[str, Any]:
    """An exposed O2M/M2M relation renders as a list of ``related model | object``
    (each record full or a partial ``{...}`` from an X-Fields selection)."""
    return {
        "anyOf": [
            {"type": "array", "items": {"anyOf": [target_ref, dict(_PARTIAL_OBJECT)]}},
            {"type": "null"},
        ],
        "default": None,
        "title": title,
    }


def _enrich_serialization_json_schema(model_cls: type, json_schema: dict[str, Any]) -> dict[str, Any]:
    """Enrich a model's serialization JSON schema in place: render foreign keys as
    ``related model | object`` and expose O2M/M2M relations as ``list[related model | object]``.

    Keeps a single schema per model (the Edgy model itself, no generated output
    class), so no two same-named schemas force FastAPI to module-qualify them."""
    properties = json_schema.get("properties")
    if properties is None:
        return json_schema

    for field_name, field in model_cls.model_fields.items():
        if _is_foreign_key_field(field):
            if field_name in properties:
                properties[field_name] = _foreign_key_json_schema(
                    properties[field_name], _target_ref(field), bool(field.null)
                )
        elif _is_exposed_relation_field(field):
            properties[field_name] = _relation_json_schema(field_name.replace("_", " ").title(), _target_ref(field))

        # auto_now / auto_now_add fields are read-only but always present in a
        # response; Pydantic drops them from `required` because they carry a
        # default_factory (for the ORM), so restore them here for the READ schema.
        if field_name in properties and (getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False)):
            required = json_schema.setdefault("required", [])
            if field_name not in required:
                required.append(field_name)

    return json_schema


def _factoryize_callable_defaults(core_schema: Any, seen: set[int]) -> None:
    """Turn a callable literal ``default`` in a core schema into a ``default_factory``.

    Edgy stores auto_now / auto_now_add as ``default=partial(datetime.now, tz)`` — a
    callable, i.e. a factory rather than a literal value. Pydantic warns when it tries
    to JSON-encode such a default into the schema; moving it to a ``default_factory``
    (which Pydantic calls, never encodes) drops the warning while the ORM keeps reading
    ``field.default`` for its own value computation."""
    if id(core_schema) in seen:
        return

    seen.add(id(core_schema))

    if isinstance(core_schema, dict):
        if (
            core_schema.get("type") == "default"
            and "default_factory" not in core_schema
            and callable(core_schema.get("default"))
        ):
            core_schema["default_factory"] = core_schema.pop("default")

        for value in core_schema.values():
            _factoryize_callable_defaults(value, seen)
    elif isinstance(core_schema, (list, tuple)):
        for value in core_schema:
            _factoryize_callable_defaults(value, seen)


class BaseModel(Model, metaclass=ModelMeta):
    id: int | None = fields.IntegerField(primary_key=True, autoincrement=True, label=_ts("ID"))

    created_at: datetime | None = fields.DateTimeField(
        default_factory=datetime.now, read_only=True, auto_now_add=True, label=_ts("Created at")
    )

    updated_at: datetime | None = fields.DateTimeField(
        default_factory=datetime.now, auto_now=True, label=_ts("Updated at")
    )

    class Meta(Meta):
        abstract = True
        exclude_secrets = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _fix_inherited_abstract(cls)
        lazy_register_model(cls)

    model_config = ConfigDict(
        extra="ignore",
    )

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
        schema = handler(source)
        _factoryize_callable_defaults(schema, set())
        return schema

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> Any:
        json_schema = handler(core_schema)
        if getattr(handler, "mode", None) != "serialization":
            return json_schema
        json_schema = handler.resolve_ref_schema(json_schema)
        return _enrich_serialization_json_schema(cls, json_schema)

    def model_dump(self, show_pk: bool | None = None, **kwargs: Any) -> dict[str, Any]:
        """Override model_dump to serialize datetime with timezone.

        `warnings=False` is set by default to silence Pydantic's
        `PydanticSerializationUnexpectedValue` for ForeignKey fields. Edgy
        annotates them with `SkipValidation()`, which re-runs the related
        model's serialiser on the raw FK id when the relation isn't loaded
        via `select_related` — the dump is correct (the int IS the FK id)
        but Pydantic flags the type mismatch on every CRUD response.
        Callers can still pass `warnings=True` (or `'error'`) explicitly to
        opt back in.
        """
        from fastedgy.serializers import datetime_serializer

        kwargs.setdefault("warnings", False)
        data = super().model_dump(show_pk=show_pk, **kwargs)

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = datetime_serializer(value)

        return data

    async def load(self, only_needed: bool = False) -> None:
        from fastedgy.orm.deferred_batch import consume_batch_load

        # Instances materialized by a column-pruned queryset reload their
        # deferred columns for the whole batch in one query (no N+1).
        if await consume_batch_load(self):
            return

        await super().load(only_needed)

    query = AccessControlManager()

    query_related = AccessControlRedirectManager(redirect_name="query")

    global_query: ClassVar[BaseManager] = Manager()

    async def save(
        self,
        force_insert: bool = False,
        values: dict[str, Any] | set[str] | None = None,
        force_save: bool | None = None,
    ) -> Self:
        from fastedgy.orm.access_guard import ModelAction, acheck_access
        from fastedgy.orm.filter.global_filters import validate_write_references

        is_update = bool(getattr(self, "_db_loaded", False) and self.pk is not None)
        await acheck_access(type(self), ModelAction.update if is_update else ModelAction.create, self)
        await validate_write_references(self)
        await super().save(force_insert=force_insert, values=values, force_save=force_save)
        return self

    async def delete(self, skip_post_delete_hooks: bool = False) -> int:
        from fastedgy.orm.access_guard import ModelAction, acheck_access

        await acheck_access(type(self), ModelAction.delete, self)
        return await super().delete(skip_post_delete_hooks=skip_post_delete_hooks)


class BaseView(Model, metaclass=ModelMeta):
    """
    Base class for defining SQL views.

    This class allows you to define SQL views directly in ORM models, without them being treated as tables by Alembic.

    Example usage:

    ```python
    from fastedgy.orm import fields
    from sqlalchemy import literal, null, select, Selectable
    from models.contact import Contact
    from models.user import User


    class MergedUserContactView(BaseView):
        class Meta(BaseView.Meta):
            tablename = "merged_user_contact_view"

        # Common Fields
        id: int = fields.IntegerField(primary_key=True)
        name: str = fields.CharField(max_length=255)
        active: bool = fields.BooleanField(default=True)

        # Contact Fields
        first_name: str | None = fields.CharField(max_length=255, null=True)
        last_name: str | None = fields.CharField(max_length=255, null=True)

        @classmethod
        def view_query(cls) -> Selectable:
            user_select = select(
                literal('user').label('source_type'),
                User.columns.id,
                User.columns.name,
                null().label('first_name'),
                null().label('last_name'),
            ).where(
                User.columns.active == True
            )

            contact_select = select(
                literal('contact').label('source_type'),
                Contact.columns.id,
                Contact.columns.full_name.label('name'),
                Contact.columns.first_name,
                Contact.columns.last_name,
            ).where(
                Contact.columns.active == True
            )

            return user_select.union(contact_select)
    ```
    """

    class Meta(Meta):
        abstract = True
        exclude_secrets = True
        is_view = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _fix_inherited_abstract(cls)
        lazy_register_model(cls)

    model_config = ConfigDict(
        extra="ignore",
    )

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
        schema = handler(source)
        _factoryize_callable_defaults(schema, set())
        return schema

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> Any:
        json_schema = handler(core_schema)
        if getattr(handler, "mode", None) != "serialization":
            return json_schema
        json_schema = handler.resolve_ref_schema(json_schema)
        return _enrich_serialization_json_schema(cls, json_schema)

    def model_dump(self, show_pk: bool | None = None, **kwargs: Any) -> dict[str, Any]:
        """Override model_dump to serialize datetime with timezone.

        `warnings=False` is set by default to silence Pydantic's
        `PydanticSerializationUnexpectedValue` for ForeignKey fields. Edgy
        annotates them with `SkipValidation()`, which re-runs the related
        model's serialiser on the raw FK id when the relation isn't loaded
        via `select_related` — the dump is correct (the int IS the FK id)
        but Pydantic flags the type mismatch on every CRUD response.
        Callers can still pass `warnings=True` (or `'error'`) explicitly to
        opt back in.
        """
        from fastedgy.serializers import datetime_serializer

        kwargs.setdefault("warnings", False)
        data = super().model_dump(show_pk=show_pk, **kwargs)

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = datetime_serializer(value)

        return data

    query = AccessControlManager()

    query_related = AccessControlRedirectManager(redirect_name="query")

    global_query: ClassVar[BaseManager] = Manager()

    @classmethod
    def build(
        cls,
        schema: Optional[str] = None,
        metadata: Optional[MetaData] = None,
    ) -> Table:
        return create_view(
            name=cls.meta.tablename,
            selectable=cls.view_query(),
            metadata=metadata,
            replace=True,
        )

    @classmethod
    @abstractmethod
    def view_query(cls) -> Selectable:
        pass


__all__ = [
    "BaseModel",
    "BaseView",
]
