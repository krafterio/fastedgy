# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import logging
from typing import Any

from edgy.core.signals import post_save
from fastedgy.orm.fields.field_fulltext import (
    get_searchable_fields,
    get_pg_language,
)

logger = logging.getLogger(__name__)

_registered_models: set[type] = set()


def register_fulltext_signals(model_cls: type) -> None:
    """
    Register a post_save signal on a model to trigger fulltext recomputation.
    Only registers once per model class.
    """
    if model_cls in _registered_models:
        return

    _registered_models.add(model_cls)

    @post_save.connect_via(model_cls)
    async def on_fulltext_save(_, instance, **kwargs: dict[str, Any]):
        await _handle_fulltext_save(instance, **kwargs)


async def _handle_fulltext_save(instance: Any, **kwargs: dict[str, Any]) -> None:
    """
    Handle post_save for fulltext recomputation.
    Recomputes tsvector inline via raw SQL.
    """
    try:
        from fastedgy import context
        from sqlalchemy import text

        model_cls = type(instance)
        searchable_fields = get_searchable_fields(model_cls)

        if not searchable_fields:
            return

        # Check if update_fields was provided (partial save)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            updated_searchable = set(update_fields) & set(searchable_fields.keys())
            if not updated_searchable:
                return

        locale = context.get_locale()
        pg_language = get_pg_language(locale)
        tablename = str(model_cls.meta.tablename)

        # Find primary key
        pk_field = None
        for fname, finfo in model_cls.meta.fields.items():
            if getattr(finfo, "primary_key", False):
                pk_field = fname
                break

        if not pk_field:
            return

        record_pk = getattr(instance, pk_field, None)
        if record_pk is None:
            return

        # Recompute each FulltextField
        for field_name, field_info in model_cls.meta.fields.items():
            if not getattr(field_info, "is_fulltext_field", False):
                continue

            column_name = f"{field_name}_{locale}"

            tsvector_parts = []
            bind_params = {"pk_value": record_pk}

            for idx, (src_field, weight) in enumerate(searchable_fields.items()):
                value = getattr(instance, src_field, None)

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
                continue

            tsvector_expr = " || ".join(tsvector_parts)
            sql = text(
                f"UPDATE {tablename} SET {column_name} = {tsvector_expr} "
                f"WHERE {pk_field} = :pk_value"
            )

            await model_cls.meta.registry.database.execute(sql, bind_params)

    except Exception:
        logger.exception("Error in fulltext post_save signal handler")


def register_all_fulltext_signals() -> None:
    """
    Scan all registered models and register fulltext signals
    for those that have at least one FulltextField with searchable source fields.
    """
    try:
        from edgy import monkay

        registry = monkay.instance.registry

        for model_cls in registry.models.values():
            has_fulltext = False
            for field_name, field_info in model_cls.meta.fields.items():
                if getattr(field_info, "is_fulltext_field", False):
                    has_fulltext = True
                    break

            if has_fulltext:
                searchable_fields = get_searchable_fields(model_cls)
                if searchable_fields:
                    register_fulltext_signals(model_cls)

    except Exception:
        logger.exception("Error registering fulltext signals")


__all__ = [
    "register_fulltext_signals",
    "register_all_fulltext_signals",
]
