# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable
from typing import Annotated, Any, cast

import sqlalchemy
from edgy.core.db.context_vars import CURRENT_PHASE
from edgy.core.db.fields.base import Field
from edgy.core.db.fields.factories import FieldFactory
from edgy.core.db.fields.types import BaseFieldType
from pydantic import ValidatorFunctionWrapHandler, WrapValidator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import BindParameter, ColumnElement
from sqlalchemy.sql.operators import OperatorType
from sqlalchemy.types import TypeDecorator

from ...i18n import TranslatableString


def _current_locale() -> str:
    from fastedgy.context import get_locale

    return get_locale()


def _fallback_locale() -> str:
    from fastedgy.context import get_fallback_locale

    return get_fallback_locale()


def _locale_param(name: str, resolve: Callable[[], str]) -> BindParameter[str]:
    # Resolved on every execution, not when the statement is compiled: the
    # compiled form is cached and shared by every locale.
    return sqlalchemy.bindparam(name, callable_=resolve, type_=sqlalchemy.Text, unique=True)


def _localized(column: Any) -> ColumnElement[str]:
    document = sqlalchemy.type_coerce(column, JSONB)
    extract = document.op("->>", return_type=sqlalchemy.Text)

    return sqlalchemy.func.coalesce(
        extract(_locale_param("locale", _current_locale)),
        extract(_locale_param("fallback_locale", _fallback_locale)),
        type_=sqlalchemy.Text,
    )


def translated(column: Any) -> Any:
    """The text a translatable column holds in the current locale, else in the fallback locale.

    Any other column is returned as it is. Comparisons and ordering already go
    through it; a SQL function taking the column (``min``, ``lower``) needs it
    spelled out."""
    if isinstance(getattr(column, "type", None), Translatable):
        return _localized(column)

    return column


class Translatable(TypeDecorator[Any]):
    """The column of a translatable field: one text per locale, ``{"en": "Chair", "fr": "Chaise"}``.

    Read, it is the text of the current locale, the fallback locale's when it
    has none: the document itself never leaves the database. Compared or
    ordered, it is that same text.

    Written, a text sets the current locale and leaves the others alone. The
    fallback locale receives it too while it has nothing, so every locale
    reads something. Writing the text a locale already reads changes nothing:
    saving a record read through the fallback does not turn that fallback into
    a translation of its own. ``None`` removes the current locale, and a column
    left with none is ``NULL``. A message marked with ``_ts`` replaces every
    locale with its translations, as a ``dict`` of the locales does.
    """

    impl = JSONB
    cache_ok = True

    def __init__(self, column_name: str | None = None) -> None:
        super().__init__()
        self.column_name = column_name

    def __repr__(self) -> str:
        return "Translatable()"

    def column_expression(self, column: Any) -> ColumnElement[str]:
        return _localized(column)

    def bind_expression(self, bindparam: BindParameter[Any]) -> ColumnElement[Any]:
        return _TranslatableWrite(bindparam, self.column_name)

    def process_bind_param(self, value: Any, dialect: Any) -> dict[str, Any]:
        if isinstance(value, TranslatableString):
            return {"replace": True, "set": translations_of(value)}

        if isinstance(value, dict):
            return {"replace": True, "set": value}

        locale = _current_locale()
        fallback = _fallback_locale()
        text = None if value is None else str(value)

        return {"read": [locale, fallback, text], "missing": {fallback: text}, "set": {locale: text}}

    def result_processor(self, dialect: Any, coltype: Any) -> None:
        return None

    class comparator_factory(TypeDecorator.Comparator[Any]):
        def operate(self, op: OperatorType, *other: Any, **kwargs: Any) -> ColumnElement[Any]:
            return cast(ColumnElement[Any], op(_localized(self.expr), *map(translated, other), **kwargs))

        def reverse_operate(self, op: OperatorType, other: Any, **kwargs: Any) -> ColumnElement[Any]:
            return cast(ColumnElement[Any], op(translated(other), _localized(self.expr), **kwargs))


def translations_of(message: TranslatableString) -> dict[str, str]:
    """The text of a message in every available locale it is translated in, the fallback and source ones always."""
    from fastedgy import context
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service, has_service

    fallback = _fallback_locale()

    if not has_service(BaseSettings):
        return {fallback: message.render()}

    settings = get_service(BaseSettings)
    kept = {fallback, settings.source_locale or fallback}
    source = message.message

    try:
        source = message.message.format(**message.kwargs) if message.kwargs else message.message
    except KeyError:
        pass
    translations: dict[str, str] = {}

    for locale in dict.fromkeys([*settings.available_locales, fallback]):
        with context.locale(locale):
            text = message.render()

        if text != source or locale in kept:
            translations[locale] = text

    return translations


class _TranslatableWrite(ColumnElement[Any]):
    """The value a translatable column is written with, built from the document it already holds."""

    inherit_cache = True

    def __init__(self, payload: BindParameter[Any], column_name: str | None) -> None:
        self.payload = payload
        self.column_name = column_name
        self.type = payload.type


@compiles(_TranslatableWrite)
def _compile_translatable_write(element: _TranslatableWrite, compiler: SQLCompiler, **kw: Any) -> str:
    payload = compiler.process(element.payload, **kw)
    current = "NULL::jsonb"
    table = getattr(compiler.statement, "table", None)

    if compiler.isupdate and table is not None:
        column = next((column for column in table.columns if column.name == element.column_name), None)

        if column is None:
            raise ValueError(f"Translatable column '{element.column_name}' not found in '{table.name}'")

        current = compiler.process(column, include_table=True)

    read = f"coalesce({current} ->> (_t.p -> 'read' ->> 0), {current} ->> (_t.p -> 'read' ->> 1))"
    kept = f"CASE WHEN _t.p ? 'replace' THEN '{{}}'::jsonb ELSE coalesce({current}, '{{}}'::jsonb) END"
    merged = (
        f"nullif(jsonb_strip_nulls(coalesce(_t.p -> 'missing', '{{}}'::jsonb) || {kept} "
        f"|| coalesce(_t.p -> 'set', '{{}}'::jsonb)), '{{}}'::jsonb)"
    )
    unchanged = f"_t.p ? 'read' AND {read} IS NOT DISTINCT FROM (_t.p -> 'read' ->> 2)"

    return f"(SELECT CASE WHEN {unchanged} THEN {current} ELSE {merged} END FROM (SELECT {payload} AS p) AS _t)"


def _keep_translatable_string(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
    # A message to translate reaches the column as it is, to be written in every locale.
    return value if isinstance(value, TranslatableString) else handler(value)


class TranslatableOptions(FieldFactory):
    """The ``translatable`` option of the text fields: one value per locale, read and written in the current one."""

    @classmethod
    def get_column_type(cls, kwargs: dict[str, Any]) -> Any:
        if kwargs.get("translatable"):
            return Translatable()

        return super().get_column_type(kwargs)

    @classmethod
    def get_pydantic_type(cls, kwargs: dict[str, Any]) -> Any:
        field_type = super().get_pydantic_type(kwargs)

        if kwargs.get("translatable"):
            return Annotated[field_type, WrapValidator(_keep_translatable_string)]

        return field_type

    # These overrides call the field class itself, never `original_fn`: Edgy
    # copies a field into every model inheriting it, and the copy keeps the
    # `original_fn` bound to the field it was copied from.

    @classmethod
    def get_column(cls, field_obj: Field, name: str, **kwargs: Any) -> sqlalchemy.Column[Any] | None:
        # The written value merges into the document the row holds, which the
        # statement reaches by the name of its column.
        if isinstance(getattr(field_obj, "column_type", None), Translatable):
            setattr(field_obj, "column_type", Translatable(getattr(field_obj, "column_name", None) or name))

        return type(field_obj).get_column(field_obj, name)

    @classmethod
    def to_model(cls, field_obj: BaseFieldType, field_name: str, value: Any, **kwargs: Any) -> dict[str, Any]:
        # Once written, the record holds the text of its locale, not the message.
        if isinstance(value, TranslatableString) and CURRENT_PHASE.get() in ("post_insert", "post_update"):
            value = str(value)

        return type(field_obj).to_model(field_obj, field_name, value)


def is_translatable(field: Any) -> bool:
    return getattr(field, "translatable", False) is True


async def read_translations(record: Any, field_name: str) -> dict[str, str]:
    """Every locale a translatable field of a stored record holds, as the row keeps them."""
    column = record.table.columns[field_name]
    statement = sqlalchemy.select(sqlalchemy.type_coerce(column, JSONB)).where(*record.identifying_clauses())

    return await record.database.fetch_val(statement) or {}


__all__ = [
    "Translatable",
    "TranslatableOptions",
    "is_translatable",
    "read_translations",
    "translated",
    "translations_of",
]
