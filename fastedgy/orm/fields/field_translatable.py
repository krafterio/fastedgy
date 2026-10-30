# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable, Iterable, Sequence
from typing import Annotated, Any, cast

import sqlalchemy
from annotated_types import MaxLen, MinLen
from edgy.core.db.context_vars import CURRENT_PHASE
from edgy.core.db.fields.base import BaseField, Field
from edgy.core.db.fields.factories import FieldFactory
from edgy.core.db.fields.types import BaseFieldType
from edgy.exceptions import FieldDefinitionError
from pydantic import GetJsonSchemaHandler, StringConstraints, ValidatorFunctionWrapHandler, WrapValidator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import BindParameter, ColumnElement
from sqlalchemy.sql.operators import OperatorType
from sqlalchemy.sql.visitors import InternalTraversal
from sqlalchemy.types import TypeDecorator

from ...i18n import TranslatableString


def _current_locale() -> str:
    from fastedgy.context import get_locale

    return get_locale()


def language_of(locale: str) -> str:
    """The language a regional locale belongs to, ``fr`` for ``fr-CA``: the locale it reads before the fallback."""
    return locale.replace("_", "-").split("-")[0]


def _current_language() -> str:
    return language_of(_current_locale())


def _fallback_locale() -> str:
    from fastedgy.context import get_fallback_locale

    return get_fallback_locale()


def available_locales() -> list[str]:
    """The locales a translatable field holds a text in, the fallback locale first."""
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service, has_service

    if not has_service(BaseSettings):
        return []

    settings = get_service(BaseSettings)

    return list(dict.fromkeys([settings.fallback_locale, *settings.available_locales]))


def _check_locales(locales: Iterable[str]) -> None:
    available = available_locales()
    unknown = [locale for locale in locales if locale not in available]

    if unknown:
        raise ValueError(f"Unavailable locale: {', '.join(unknown)} (available: {', '.join(available)})")


def _locale_param(name: str, resolve: Callable[[], str]) -> BindParameter[str]:
    # Resolved on every execution, not when the statement is compiled: the
    # compiled form is cached and shared by every locale.
    return sqlalchemy.bindparam(name, callable_=resolve, type_=sqlalchemy.Text, unique=True)


# The text of a document holding a single locale, whichever it is, outside the
# available ones: what is left to read once the fallback changed and no available
# locale is held. One holding several reads none, the order of its keys meaning nothing.
SOLE_TEXT_PATH = "strict $ ? (@.size() == 1)"
SOLE_TEXT_SQL = "jsonb_path_query_first(jsonb_path_query_array({document}, '$.*'), '" + SOLE_TEXT_PATH + "') ->> 0"


def _sole_text(document: Any) -> ColumnElement[str]:
    texts = sqlalchemy.func.jsonb_path_query_array(document, sqlalchemy.literal_column("'$.*'"))
    sole = sqlalchemy.func.jsonb_path_query_first(texts, sqlalchemy.literal_column(f"'{SOLE_TEXT_PATH}'"))

    return sole.op("->>", return_type=sqlalchemy.Text)(sqlalchemy.literal_column("0"))


def _available_text_sql(document: str, locales: str) -> str:
    """The text of the first of ``locales`` (a set of texts, in order) the document holds."""
    return (
        f"(SELECT {document} ->> _available.locale FROM {locales} WITH ORDINALITY "
        f"AS _available(locale, position) WHERE {document} ? _available.locale "
        f"ORDER BY _available.position LIMIT 1)"
    )


class _AvailableText(ColumnElement[str]):
    """The text of the first available locale a document holds, in the order of the settings."""

    inherit_cache = True
    _traverse_internals = [
        ("document", InternalTraversal.dp_clauseelement),
        ("locales", InternalTraversal.dp_clauseelement),
    ]

    def __init__(self, document: ColumnElement[Any]) -> None:
        self.document = document
        # The list is bound, not compiled in: the compiled form is shared by every settings.
        self.locales = sqlalchemy.bindparam(
            "available_locales", callable_=available_locales, type_=ARRAY(sqlalchemy.Text), unique=True
        )
        self.type = sqlalchemy.Text()


@compiles(_AvailableText)
def _compile_available_text(element: _AvailableText, compiler: SQLCompiler, **kw: Any) -> str:
    locales = f"unnest({compiler.process(element.locales, **kw)})"

    return _available_text_sql(compiler.process(element.document, **kw), locales)


def _localized(column: Any) -> ColumnElement[str]:
    document = sqlalchemy.type_coerce(column, JSONB)
    extract = document.op("->>", return_type=sqlalchemy.Text)

    return sqlalchemy.func.coalesce(
        extract(_locale_param("locale", _current_locale)),
        extract(_locale_param("language", _current_language)),
        extract(_locale_param("fallback_locale", _fallback_locale)),
        _AvailableText(document),
        _sole_text(document),
        type_=sqlalchemy.Text,
    )


def translated(column: Any) -> Any:
    """The text a translatable column reads in the current locale, as a select of it gives it.

    Any other column is returned as it is. Comparisons and ordering already go
    through it; a SQL function taking the column (``min``, ``lower``) needs it
    spelled out."""
    if isinstance(getattr(column, "type", None), Translatable):
        return _localized(column)

    return column


class Translatable(TypeDecorator[Any]):
    """The column of a translatable field: one text per locale, ``{"en": "Chair", "fr": "Chaise"}``.

    Read, it is the text of the current locale, else of its language (``fr``
    for ``fr-CA``), else of the fallback locale, else of the first available
    locale it holds in the order of the settings, else the text of its only
    locale, ``NULL`` for a document holding several others: the document
    itself never leaves the database. Compared or ordered, it is that same text.

    Written, a text sets the current locale and leaves the others alone. The
    fallback locale receives it too while it has nothing, so every locale
    reads something. Writing the text a locale already reads changes nothing:
    saving a record read through the fallback does not turn that fallback into
    a translation of its own. ``None`` removes the current locale, and a column
    left with none is ``NULL``. A ``dict`` of locales sets each of them the
    same way, and a message marked with ``_ts`` replaces every locale with its
    translations. A locale outside the available ones is refused.
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

        fallback = _fallback_locale()

        if isinstance(value, dict):
            _check_locales(value)
            texts = {locale: None if text is None else str(text) for locale, text in value.items()}
            first = next((text for text in texts.values() if text is not None), None)

            return {"missing": {fallback: first}, "set": texts}

        locale = _current_locale()
        text = None if value is None else str(value)
        _check_locales([locale])

        return {
            "read": [locale, language_of(locale), fallback, text],
            "available": available_locales(),
            "missing": {fallback: text},
            "set": {locale: text},
        }

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

    reads = ", ".join(f"{current} ->> (_t.p -> 'read' ->> {index})" for index in range(3))
    available = _available_text_sql(current, "jsonb_array_elements_text(_t.p -> 'available')")
    read = f"coalesce({reads}, {available}, {SOLE_TEXT_SQL.format(document=current)})"
    kept = f"CASE WHEN _t.p ? 'replace' THEN '{{}}'::jsonb ELSE coalesce({current}, '{{}}'::jsonb) END"
    merged = (
        f"nullif(jsonb_strip_nulls(coalesce(_t.p -> 'missing', '{{}}'::jsonb) || {kept} "
        f"|| coalesce(_t.p -> 'set', '{{}}'::jsonb)), '{{}}'::jsonb)"
    )
    unchanged = f"_t.p ? 'read' AND {read} IS NOT DISTINCT FROM (_t.p -> 'read' ->> 3)"

    return f"(SELECT CASE WHEN {unchanged} THEN {current} ELSE {merged} END FROM (SELECT {payload} AS p) AS _t)"


class _AvailableLocale:
    """A key of the translations a write takes: its schema lists the available locales."""

    def __get_pydantic_json_schema__(self, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(schema)
        locales = available_locales()

        if locales:
            json_schema["enum"] = locales

        return json_schema


TranslationLocale = Annotated[str, _AvailableLocale()]
"""A locale keying the translations of a field: an available one."""


def _validate_translations(nullable: bool) -> Callable[[Any, ValidatorFunctionWrapHandler], Any]:
    def validate(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        # A message to translate reaches the column as it is, to be written in every locale.
        if isinstance(value, TranslatableString):
            return value

        if not isinstance(value, dict):
            return handler(value)

        _check_locales(value)
        fallback = _fallback_locale()

        if not nullable and fallback in value and value[fallback] is None:
            raise ValueError(f"The text of the fallback locale {fallback} is required")

        return {locale: None if text is None else handler(text) for locale, text in value.items()}

    return validate


def _bounds_text(metadata: Any) -> bool:
    return isinstance(metadata, MaxLen | MinLen) or getattr(metadata, "pattern", None) is not None


def _written_text(document: dict[str, Any]) -> Any:
    """What the current locale reads in the translations just written: theirs, its language's, the fallback's, which a
    write naming none fills from its first text."""
    for locale in (_current_locale(), _current_language(), _fallback_locale()):
        if document.get(locale) is not None:
            return document[locale]

    return next((text for text in document.values() if text is not None), None)


class TranslatableOptions(FieldFactory):
    """The ``translatable`` option of the text fields: one value per locale, read and written in the current one."""

    @classmethod
    def get_column_type(cls, kwargs: dict[str, Any]) -> Any:
        if kwargs.get("translatable"):
            return Translatable()

        return super().get_column_type(kwargs)

    @classmethod
    def validate(cls, kwargs: dict[str, Any]) -> None:
        super().validate(kwargs)

        if kwargs.get("translatable") and (kwargs.get("unique") or kwargs.get("primary_key")):
            raise FieldDefinitionError(
                detail="A translatable field can be neither unique nor a primary key: it holds one text per locale"
            )

    @classmethod
    def get_pydantic_type(cls, kwargs: dict[str, Any]) -> Any:
        field_type = super().get_pydantic_type(kwargs)

        if not kwargs.get("translatable"):
            return field_type

        # A write takes a text, or its translations keyed by locale: in JSON
        # `"Chair"` or `{"en": "Chair", "fr": "Chaise"}`. A read gives the text.
        text = Annotated[
            field_type,
            StringConstraints(
                min_length=kwargs.get("min_length"),
                max_length=kwargs.get("max_length"),
                pattern=kwargs.get("pattern"),
            ),
        ]
        translations = dict[TranslationLocale, text | None]
        validator = WrapValidator(
            _validate_translations(bool(kwargs.get("null"))),
            json_schema_input_type=text | translations,
        )

        return Annotated[text, validator]

    @classmethod
    def build_field(cls, **kwargs: Any) -> BaseFieldType:
        field = super().build_field(**kwargs)

        # The text type carries the length and the pattern: on the field, they
        # would bound the translations a write takes by their count of locales.
        if kwargs.get("translatable") and isinstance(field, BaseField):
            field.metadata = [metadata for metadata in field.metadata if not _bounds_text(metadata)]

        return field

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
        phase = CURRENT_PHASE.get()

        # A record built by a caller is one to create: a required field takes a
        # text in one locale at least, where an update may clear any but the fallback.
        if (
            phase == "init"
            and is_translatable(field_obj)
            and not field_obj.null
            and isinstance(value, dict)
            and all(text is None for text in value.values())
        ):
            raise ValueError(f"The translatable field {field_name} takes at least one text")

        # Once written, the record holds the text of its locale, not the
        # message or the translations. After an update with translations
        # missing that locale, the text is the one they lead it to read: a
        # load reads what the row holds.
        if phase in ("post_insert", "post_update"):
            if isinstance(value, TranslatableString):
                value = str(value)
            elif isinstance(value, dict):
                value = _written_text(value)

        return type(field_obj).to_model(field_obj, field_name, value)


def is_translatable(field: Any) -> bool:
    return getattr(field, "translatable", False) is True


def translatable_fields(model_cls: Any) -> list[str]:
    """The names of the translatable fields of a model."""
    return [name for name, field in model_cls.meta.fields.items() if is_translatable(field)]


async def fetch_translations(
    model_cls: Any,
    keys: Iterable[Any],
    field_names: Sequence[str] | None = None,
) -> dict[Any, dict[str, dict[str, str]]]:
    """Every locale the translatable fields of stored records hold, by primary key, read in one statement.

    A record left out of the answer is not stored; a field holding nothing gives ``{}``.
    """
    names = list(field_names) if field_names is not None else translatable_fields(model_cls)
    keys = list(keys)

    if not names or not keys:
        return {}

    table = model_cls.table
    key = table.columns[model_cls.pkcolumns[0]]
    documents = [
        sqlalchemy.type_coerce(table.columns[name], JSONB).label(f"document_{i}") for i, name in enumerate(names)
    ]
    rows = await model_cls.database.fetch_all(
        sqlalchemy.select(key.label("record_key"), *documents).where(key.in_(keys))
    )

    return {
        row._mapping["record_key"]: {name: row._mapping[f"document_{i}"] or {} for i, name in enumerate(names)}
        for row in rows
    }


async def read_translations(record: Any, field_name: str) -> dict[str, str]:
    """Every locale a translatable field of a stored record holds, as the row keeps them."""
    column = record.table.columns[field_name]
    statement = sqlalchemy.select(sqlalchemy.type_coerce(column, JSONB)).where(*record.identifying_clauses())

    return await record.database.fetch_val(statement) or {}


__all__ = [
    "SOLE_TEXT_SQL",
    "Translatable",
    "TranslatableOptions",
    "TranslationLocale",
    "available_locales",
    "fetch_translations",
    "is_translatable",
    "language_of",
    "read_translations",
    "translatable_fields",
    "translated",
    "translations_of",
]
