# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import logging
from collections.abc import Sequence
from functools import cache
from typing import TYPE_CHECKING, Any, Literal, cast

import sqlalchemy
from edgy.core.db.fields import (
    CharField,
    EmailField,
    TextField,
)
from edgy.core.db.fields.base import BaseField
from edgy.core.db.fields.types import BaseFieldType
from sqlalchemy.dialects.postgresql import TSVECTOR

from .field_html import HTMLField
from .field_phone import PhoneField

if TYPE_CHECKING:
    from fastedgy.models.base import BaseModel

logger = logging.getLogger(__name__)


SearchWeight = Literal["A", "B", "C", "D"]

SEARCH_WEIGHT_FIELD_MAP: dict[type, SearchWeight] = {
    CharField: "A",
    TextField: "B",
    HTMLField: "C",
    PhoneField: "D",
    EmailField: "D",
}


def resolve_search_weight(field_info: BaseFieldType) -> SearchWeight | None:
    """
    Resolve the search weight for a field.

    - If searchable is a string ("A", "B", "C", "D") → use it directly
    - If searchable is True → resolve from SEARCH_WEIGHT_FIELD_MAP via MRO
    - If searchable is False or not found → return None (not indexed)
    - If searchable is not set → resolve from SEARCH_WEIGHT_FIELD_MAP via MRO
    """
    searchable = getattr(field_info, "searchable", None)

    if isinstance(searchable, str):
        return cast(SearchWeight, searchable)

    if searchable is False:
        return None

    if searchable is None and getattr(field_info, "exclude", False):
        return None

    # searchable is True or not set → resolve from map via isinstance
    for map_type, weight in SEARCH_WEIGHT_FIELD_MAP.items():
        if isinstance(field_info, map_type):
            return weight

    # Not in map: if searchable was explicitly True, default to "D"
    if searchable is True:
        return "D"

    return None


@cache
def get_searchable_fields(
    model_cls: "type[BaseModel]",
) -> dict[str, SearchWeight]:
    """
    Discover all searchable fields on a model and their weights.
    Cached per model class via lru_cache.

    Returns:
        dict mapping field name to weight ("A", "B", "C", "D")
    """
    result: dict[str, SearchWeight] = {}

    for field_name, field_info in model_cls.meta.fields.items():
        if getattr(field_info, "is_fulltext_field", False):
            continue

        weight = resolve_search_weight(field_info)
        if weight is not None:
            result[field_name] = weight

    return result


def _get_available_locales() -> list[str]:
    """Get available locales from settings. Falls back to ["en"]."""
    try:
        from fastedgy.config import BaseSettings
        from fastedgy.dependencies import get_service

        settings = get_service(BaseSettings)
        return settings.available_locales
    except Exception:
        return ["en"]


class FulltextField(BaseField):
    """
    PostgreSQL tsvector field for full-text search.
    Generates one tsvector column per locale in settings.available_locales.
    Fully excluded from API read and write — internal use only.

    Discovers source fields automatically by scanning the model for fields
    with searchable != False. Weights are resolved per field type via
    SEARCH_WEIGHT_FIELD_MAP, or overridden explicitly with searchable="A".

    Usage:
        class Task(BaseModel):
            name = fields.CharField(max_length=255)              # searchable="A" (default CharField)
            description = fields.TextField(null=True)             # searchable="B" (default TextField)
            priority = fields.IntegerField(default=0)             # searchable=False (default)
            notes = fields.TextField(null=True, searchable=False) # override: not indexed
            search_value = fields.FulltextField()                 # discovers name + description

    Generates columns: search_value_fr, search_value_en, etc.
    based on settings.available_locales at migration time.
    """

    is_fulltext_field = True

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("exclude", True)
        kwargs.setdefault("filterable", True)
        kwargs.setdefault("copy", False)
        kwargs["null"] = True
        kwargs["primary_key"] = False
        kwargs["field_type"] = kwargs["annotation"] = Any
        super().__init__(**kwargs)

    def get_columns(self, name: str) -> Sequence[sqlalchemy.Column]:
        """Generate one TSVECTOR column per locale in settings.available_locales."""
        locales = _get_available_locales()
        columns = []
        for locale in locales:
            col_name = f"{name}_{locale}"
            columns.append(sqlalchemy.Column(col_name, TSVECTOR, nullable=True))
        return columns

    def get_global_constraints(
        self,
        name: str,
        columns: Sequence[sqlalchemy.Column],
        schemes: Sequence[str] = (),
    ) -> Sequence[sqlalchemy.Index]:
        """Generate one GIN index per tsvector column."""
        locales = _get_available_locales()
        tablename = str(self.owner.meta.tablename) if hasattr(self, "owner") and self.owner else "unknown"
        indexes = []
        for locale in locales:
            col_name = f"{name}_{locale}"
            for col in columns:
                if col.name == col_name:
                    indexes.append(
                        sqlalchemy.Index(
                            f"idx_{tablename}_{col_name}_gin",
                            col,
                            postgresql_using="gin",
                        )
                    )
                    break
        return indexes

    def to_model(self, field_name: str, value: Any) -> dict[str, Any]:
        return {}

    def clean(self, field_name: str, value: Any, for_query: bool = False) -> dict[str, Any]:
        return {}

    def __get__(self, instance: Any, owner: Any = None) -> None:
        return None

    def __set__(self, instance: Any, value: Any) -> None:
        pass


def get_pg_language(locale: str) -> str:
    """Resolve a locale to a PostgreSQL language name via Babel."""
    try:
        from babel import Locale as BabelLocale

        return (BabelLocale.parse(locale).english_name or "simple").lower()
    except Exception:
        return "simple"


def escape_sql(value: str) -> str:
    """Escape single quotes for SQL string literals."""
    return value.replace("'", "''")


def is_view_model(model_cls: type) -> bool:
    """
    Whether the model is mapped onto a SQL view rather than a table.

    A view holding a tsvector column computes it in its own SELECT, and
    PostgreSQL refuses to update one that is not automatically updatable, so
    nothing here may write to it.

    The class is what settles it, not the Meta flag: a view is free to declare
    a bare `class Meta:` instead of inheriting `BaseView.Meta`, and then it
    carries no is_view at all. The flag is still honoured, for a model mapped
    onto a view it does not subclass.
    """
    from fastedgy.models.base import BaseView

    if getattr(getattr(model_cls, "Meta", None), "is_view", False):
        return True

    return isinstance(model_cls, type) and issubclass(model_cls, BaseView)


def get_primary_key_field(model_cls: "type[BaseModel]") -> str | None:
    """Name of the model's primary key field, if it has a single one."""
    for name, field_info in model_cls.meta.fields.items():
        if getattr(field_info, "primary_key", False):
            return name

    return None


def build_tsvector_expression(model_cls: "type[BaseModel]", locale: str) -> str | None:
    """
    Build the SQL expression computing the tsvector of a record, for one locale.

    The expression reads the table's own columns, never Python values: a partial
    save carries only the fields it loaded, and feeding those to the tsvector
    would drop every word held by a column the instance never read. The record
    would then flip between a complete and a truncated vector on alternating
    saves, rewriting the GIN index each time.

    Returns None when the model has nothing searchable.
    """
    searchable_fields = get_searchable_fields(model_cls)

    if not searchable_fields:
        return None

    pg_language = get_pg_language(locale)
    columns = model_cls.table.columns
    parts: list[str] = []

    for src_field, weight in searchable_fields.items():
        column = columns.get(src_field)

        if column is None:
            continue

        quoted = f'"{column.name}"'

        if isinstance(column.type, sqlalchemy.JSON):
            source = f"{quoted} ->> '{escape_sql(locale)}'"
        else:
            source = f"{quoted}::text"

        parts.append(f"setweight(to_tsvector('{pg_language}', unaccent(coalesce({source}, ''))), '{weight}')")

    if not parts:
        return None

    return " || ".join(parts)


def get_fulltext_column(model_cls: "type[BaseModel]", field_name: str, locale: str) -> str | None:
    """Resolve the tsvector column of a FulltextField for one locale, if it exists."""
    column = model_cls.table.columns.get(f"{field_name}_{locale}")

    return column.name if column is not None else None


async def recompute_fulltext(
    model_class_path: str,
    record_pk: Any,
    fulltext_field_name: str,
    locale: str,
) -> None:
    """
    Recompute the tsvector for a single record and a single locale.
    Uses raw SQL to bypass signals and avoid infinite loops.

    Args:
        model_class_path: Dotted path to the model class (e.g. "models.task.Task")
        record_pk: Primary key of the record to update
        fulltext_field_name: Name of the FulltextField on the model (e.g. "search_value")
        locale: Locale to compute (e.g. "fr")
    """
    import importlib

    try:
        parts = model_class_path.rsplit(".", 1)
        module = importlib.import_module(parts[0])
        model_cls = getattr(module, parts[1])

        expression = build_tsvector_expression(model_cls, locale)

        if expression is None:
            return

        column_name = get_fulltext_column(model_cls, fulltext_field_name, locale)

        if column_name is None:
            return

        pk_field = get_primary_key_field(model_cls)

        if pk_field is None:
            return

        from sqlalchemy import text

        tablename = str(model_cls.meta.tablename)
        target = f'"{column_name}"'
        sql = text(
            f"UPDATE {tablename} SET {target} = {expression} "
            f'WHERE "{pk_field}" = :pk_value AND {target} IS DISTINCT FROM ({expression})'
        )

        await model_cls.meta.registry.database.execute(sql, {"pk_value": record_pk})

    except Exception:
        logger.exception(
            f"Failed to recompute fulltext for {model_class_path} "
            f"pk={record_pk} field={fulltext_field_name} locale={locale}"
        )


__all__ = [
    "SEARCH_WEIGHT_FIELD_MAP",
    "FulltextField",
    "SearchWeight",
    "build_tsvector_expression",
    "escape_sql",
    "get_fulltext_column",
    "get_pg_language",
    "get_primary_key_field",
    "is_view_model",
    "get_searchable_fields",
    "recompute_fulltext",
    "resolve_search_weight",
]
