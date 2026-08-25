# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import logging
from typing import Any

from edgy.core.signals import post_save
from sqlalchemy.exc import DBAPIError

from fastedgy.orm.fields.field_fulltext import (
    build_tsvector_expression,
    get_fulltext_column,
    get_primary_key_field,
    get_searchable_fields,
    is_view_model,
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
    async def on_fulltext_save(_, instance, model_instance=None, **kwargs: dict[str, Any]):
        target = model_instance if model_instance is not None else instance
        await _handle_fulltext_save(target, **kwargs)


async def _handle_fulltext_save(instance: Any, **kwargs: dict[str, Any]) -> None:
    """
    Handle post_save for fulltext recomputation.
    Recomputes tsvector inline via raw SQL.
    """
    try:
        from sqlalchemy import text

        from fastedgy import context

        model_cls = type(instance)
        searchable_fields = get_searchable_fields(model_cls)

        if not searchable_fields:
            return

        # Only a create, or an update that actually wrote a searchable column,
        # can change the tsvector. Edgy hands the written field names in
        # `values` and the written column names in `column_values`; on anything
        # else the statement below would be a pure round-trip for a record whose
        # indexed text nobody touched.
        if kwargs.get("is_update"):
            written = set(kwargs.get("values") or ()) | set(kwargs.get("column_values") or ())

            if not written & set(searchable_fields):
                return

        locale = context.get_locale()
        expression = build_tsvector_expression(model_cls, locale)

        if expression is None:
            return

        pk_field = get_primary_key_field(model_cls)

        if pk_field is None:
            return

        record_pk = instance.__dict__.get(pk_field)

        if record_pk is None:
            return

        tablename = str(model_cls.meta.tablename)

        for field_name, field_info in model_cls.meta.fields.items():
            if not getattr(field_info, "is_fulltext_field", False):
                continue

            column_name = get_fulltext_column(model_cls, field_name, locale)

            if column_name is None:
                continue

            target = f'"{column_name}"'
            # Skip the write entirely when the recomputed tsvector is unchanged:
            # a no-op UPDATE would still create a new row version (heap + every
            # index incl. the GIN) and generate WAL on every save of the record.
            sql = text(
                f"UPDATE {tablename} SET {target} = {expression} "
                f'WHERE "{pk_field}" = :pk_value AND {target} IS DISTINCT FROM ({expression})'
            )

            await model_cls.meta.registry.database.execute(sql, {"pk_value": record_pk})

    except DBAPIError:
        # A database error here (typically a serialization conflict 40001 under
        # concurrent writes) has already aborted the surrounding transaction.
        # Swallowing it would leave the transaction poisoned and make the very
        # next statement in the post_save chain (or after save()) fail with a
        # misleading InFailedSQLTransactionError. Propagate so the caller's
        # transaction/retry machinery rolls back and replays cleanly — the
        # tsvector UPDATE is idempotent, so replay is safe.
        raise
    except Exception:
        logger.exception("Error in fulltext post_save signal handler")


def register_all_fulltext_signals() -> None:
    """
    Scan all registered models and register fulltext signals
    for those that have at least one FulltextField with searchable source fields.
    """
    try:
        from fastedgy.dependencies import get_service
        from fastedgy.orm import Registry

        registry = get_service(Registry)

        for model_cls in registry.models.values():
            if is_view_model(model_cls):
                continue

            has_fulltext = False
            for field_info in model_cls.meta.fields.values():
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
    "register_all_fulltext_signals",
    "register_fulltext_signals",
]
