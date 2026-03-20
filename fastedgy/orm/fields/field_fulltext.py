# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Literal, Sequence

import sqlalchemy
from sqlalchemy.dialects.postgresql import TSVECTOR

from edgy.core.db.fields import (
    CharField,
    EmailField,
    TextField,
)
from edgy.core.db.fields.base import BaseField
from edgy.core.db.fields.types import BaseFieldType

from .field_html import HTMLField
from .field_phone import PhoneField

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
        return searchable

    if searchable is False:
        return None

    # searchable is True or not set → resolve from map via isinstance
    for map_type, weight in SEARCH_WEIGHT_FIELD_MAP.items():
        if isinstance(field_info, map_type):
            return weight

    # Not in map: if searchable was explicitly True, default to "D"
    if searchable is True:
        return "D"

    return None


@lru_cache(maxsize=None)
def get_searchable_fields(
    model_cls: type,
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
        indexes = []
        for locale in locales:
            col_name = f"{name}_{locale}"
            # Find the matching column
            for col in columns:
                if col.name == col_name:
                    indexes.append(
                        sqlalchemy.Index(
                            f"idx_{col_name}_gin",
                            col,
                            postgresql_using="gin",
                        )
                    )
                    break
        return indexes

    def to_model(self, field_name: str, value: Any) -> dict[str, Any]:
        return {}

    def clean(self, name: str, value: Any, for_query: bool = False) -> dict[str, Any]:
        return {}

    def __get__(self, instance: Any, owner: Any = None) -> None:
        return None

    def __set__(self, instance: Any, value: Any) -> None:
        pass


def get_pg_language(locale: str) -> str:
    """Resolve a locale to a PostgreSQL language name via Babel."""
    try:
        from babel import Locale as BabelLocale

        return BabelLocale.parse(locale).english_name.lower()
    except Exception:
        return "simple"


def escape_sql(value: str) -> str:
    """Escape single quotes for SQL string literals."""
    return value.replace("'", "''")


async def recompute_fulltext(
    model_class_path: str,
    record_pk: any,
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
        # Resolve model class from path
        parts = model_class_path.rsplit(".", 1)
        module = importlib.import_module(parts[0])
        model_cls = getattr(module, parts[1])

        # Get searchable fields and their weights
        searchable_fields = get_searchable_fields(model_cls)
        if not searchable_fields:
            return

        # Load the record to get field values
        pk_field = None
        for fname, finfo in model_cls.meta.fields.items():
            if getattr(finfo, "primary_key", False):
                pk_field = fname
                break

        if not pk_field:
            return

        record = await model_cls.query.filter(**{pk_field: record_pk}).first()
        if not record:
            return

        # Build the tsvector expression parts
        pg_language = get_pg_language(locale)
        tablename = str(model_cls.meta.tablename)
        column_name = f"{fulltext_field_name}_{locale}"

        tsvector_parts = []
        bind_params = {"pk_value": record_pk}

        for idx, (field_name, weight) in enumerate(searchable_fields.items()):
            value = getattr(record, field_name, None)

            # Handle translatable dict fields
            if isinstance(value, dict):
                value = value.get(locale)

            if value is None:
                value = ""
            else:
                value = str(value)

            param_name = f"val_{idx}"
            bind_params[param_name] = value
            tsvector_parts.append(
                f"setweight(to_tsvector('{pg_language}', unaccent(coalesce(:{param_name}, ''))), '{weight}')"
            )

        if not tsvector_parts:
            return

        tsvector_expr = " || ".join(tsvector_parts)

        # Execute raw SQL update
        from sqlalchemy import text

        sql = text(
            f"UPDATE {tablename} SET {column_name} = {tsvector_expr} "
            f"WHERE {pk_field} = :pk_value"
        )

        await model_cls.meta.registry.database.execute(sql, bind_params)

    except Exception:
        logger.exception(
            f"Failed to recompute fulltext for {model_class_path} "
            f"pk={record_pk} field={fulltext_field_name} locale={locale}"
        )


__all__ = [
    "SearchWeight",
    "SEARCH_WEIGHT_FIELD_MAP",
    "resolve_search_weight",
    "get_searchable_fields",
    "get_pg_language",
    "escape_sql",
    "recompute_fulltext",
    "FulltextField",
]
