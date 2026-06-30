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
    WorkspaceableManager,
    WorkspaceableRedirectManager,
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
    if TYPE_CHECKING:

        def __hash__(self) -> int: ...


def _fix_inherited_abstract(cls: type) -> None:
    """Edgy's metaclass detects ``abstract`` via ``getattr(meta_class, "abstract", False)``
    which traverses the MRO. Subclasses that extend ``BaseModel.Meta`` or
    ``BaseView.Meta`` therefore silently inherit ``abstract = True`` and are
    excluded from registration. Reset it for concrete subclasses that have
    their own fields but did not explicitly opt into abstract.
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

    if "pk" not in cls.meta.fields:
        from edgy.core.db.fields.base import PKField

        pk_field = PKField(exclude=True, name="pk", inherit=False, no_copy=True)
        pk_field.owner = cls
        cls.meta.fields["pk"] = pk_field
        model_fields_on_class = getattr(cls, "__pydantic_fields__", None)
        if model_fields_on_class is None:
            model_fields_on_class = getattr(cls, "model_fields", None)
        if model_fields_on_class is not None:
            model_fields_on_class["pk"] = pk_field


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

    query = WorkspaceableManager()

    query_related = WorkspaceableRedirectManager(redirect_name="query")

    global_query: ClassVar[BaseManager] = Manager()

    async def save(
        self,
        force_insert: bool = False,
        values: dict[str, Any] | set[str] | None = None,
        force_save: bool | None = None,
    ) -> Self:
        await super().save(force_insert=force_insert, values=values, force_save=force_save)
        return self


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

    query = WorkspaceableManager()

    query_related = WorkspaceableRedirectManager(redirect_name="query")

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
