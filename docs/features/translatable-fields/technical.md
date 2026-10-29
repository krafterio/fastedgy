# Translatable fields - Technical details

## Architecture

The whole feature lives in one SQLAlchemy type, `Translatable` (`fastedgy/orm/fields/field_translatable.py`), the column type of a field declared `translatable=True`. Edgy builds its queries from the columns, so every read, comparison and write of the column goes through the type:

| Hook | Role |
|------|------|
| `column_expression` | Replaces the column in a `SELECT` by the text of the current locale |
| `comparator_factory` | Compares, orders and matches that same text |
| `process_bind_param` | Turns the written value into a payload describing the write |
| `bind_expression` | Merges the payload into the document the row holds |

`TranslatableOptions` is the factory mixin of `CharField`, `TextField`, `RichTextField` and `HTMLField`. With the option set, it gives the field the `Translatable` column type, refuses `unique` and `primary_key`, and builds its Pydantic type:

- the text, carrying `max_length`, `min_length` and `pattern`, which leave the field itself: there they would bound a dict of translations by its count of locales;
- a wrap validator taking that text, a `_ts()` message as it is, or a dict of available locales whose each text is validated as the text;
- `json_schema_input_type`, so the validation schema (request bodies) is `text | {locale: text | null}` and the serialization schema (responses) the text alone. The keys list the available locales when the schema is generated.

## Reading

```sql
SELECT coalesce(products.name ->> $1, products.name ->> $2) AS name FROM products
```

The two locales are bound parameters resolved on every execution, not compiled into the SQL: the compiled statement is cached and shared by every locale. The column's result processor is disabled, so the driver hands back the text as it is.

## Comparing and ordering

The comparator rewrites every operator applied to the column on the localized text, so `==`, `ilike`, `in_`, `is_`, `match`, `asc` and `desc` all compare the text a read returns. The ascending terms of `order_by()`, which Edgy passes as the bare column, and the aggregate ordering a record by a to-many relation are wrapped by `translated()` in `QuerySet._prepare_order_by` and `aggregated_relation_column`.

## Writing

The value bound for the column is a payload:

| Value | Payload |
|-------|---------|
| `str` or `None` | `{"read": [locale, fallback, text], "missing": {fallback: text}, "set": {locale: text}}` |
| `dict` | `{"missing": {fallback: first text}, "set": {locale: text, ...}}` |
| `TranslatableString` | `{"replace": true, "set": {locale: translation, ...}}` |

The locales of a `str` or a `dict` must be available ones: the bind raises a `ValueError` otherwise, the last check of a write that skipped validation (`update()`, `QuerySet.update()`).

`bind_expression` wraps it in a scalar subquery merging it into the current document, `NULL` on an insert:

```sql
SET name = (
  SELECT CASE
    WHEN _t.p ? 'read'
     AND coalesce(name ->> (_t.p -> 'read' ->> 0), name ->> (_t.p -> 'read' ->> 1))
         IS NOT DISTINCT FROM (_t.p -> 'read' ->> 2)
    THEN name
    ELSE nullif(jsonb_strip_nulls(
      coalesce(_t.p -> 'missing', '{}') ||
      CASE WHEN _t.p ? 'replace' THEN '{}' ELSE coalesce(name, '{}') END ||
      coalesce(_t.p -> 'set', '{}')
    ), '{}')
  END
  FROM (SELECT $1::JSONB AS p) AS _t
)
```

- `missing` comes first in the merge: it fills the fallback locale only when the document has none.
- `read` skips the write when the text equals what the locale reads already. Edgy saves every loaded field, so without it a record read through the fallback would store the fallback as a translation on its next save.
- A locale set to `null` is dropped by `jsonb_strip_nulls`, and an empty document becomes `NULL`.

The update reaches the row's document by the name of its column, which `TranslatableOptions.get_column` gives the type. Since the merge is SQL, every write path behaves the same: `save()`, `update()`, `QuerySet.update()`, `bulk_create()` and `bulk_update()`, which binds the column through `executemany`.

## Locale context

`fastedgy.context` resolves the locale from a `with context.locale(...)` block first, then the request, then the fallback locale. Outside a request, `set_locale()` sets it for the current context. The queue stores the locale a task is created in under `_locale` in its context and restores it before the run, the run of a sync function included, which executes in a copy of the context.

## Full-text search

`build_tsvector_expression` reads a translatable source as `coalesce(col ->> 'fr', col ->> 'en')`. The save signal recomputes the vector of every available locale in one `UPDATE`, skipped when no vector changes: a write in one locale may fill the fallback, and every locale without a text of its own reads it.

## Migrations

`process_translatable_revision_directives` runs within `fastedgy_process_revision_directives`. On the upgrade and downgrade operations, it replaces the type change of an `alter_column`:

| From | To | Operation | `USING` |
|------|----|-----------|---------|
| `VARCHAR`, `TEXT` | `Translatable` | `convert_to_translatable` | `CASE WHEN col IS NULL THEN NULL ELSE jsonb_build_object('en', col) END` |
| `Translatable`, `JSONB` | `VARCHAR`, `TEXT` | `convert_from_translatable` | `col ->> 'en'` |

Alembic renders no `postgresql_using`, hence the operations of their own. The fallback locale is the one configured when the migration is generated. The rest of an `alter_column` (nullability, default, comment) stays in place after the conversion. A `Translatable` column compiles to `JSONB`, so a schema in line with the models produces no migration.

## Reference

| Name | Module | Description |
|------|--------|-------------|
| `Translatable` | `fastedgy.orm.fields` | Column type of a translatable field |
| `translated(column)` | `fastedgy.orm.fields` | The text of the current locale, any other column unchanged |
| `is_translatable(field)` | `fastedgy.orm.fields` | Whether a field is declared `translatable=True` |
| `read_translations(record, name)` | `fastedgy.orm.fields` | Every locale a stored record holds |
| `translations_of(message)` | `fastedgy.orm.fields` | The translations a `_ts()` message writes |
| `context.locale(code)` | `fastedgy.context` | Read and write in a locale for a block |
| `translatable_from_text`, `text_from_translatable` | `fastedgy.orm.migration` | SQL of the conversions, for hand-written migrations |

## Limits

- A read returns one locale: an API read gives one language, `read_translations()` gives every locale in Python.
- Changing `fallback_locale` later leaves the stored documents as they are: a record without the new fallback reads `None` in a locale it has no text in.
- `distinct("name")` on a translatable field compares the stored documents, and cannot lead an `order_by("name")`.
- After an `update()` with a dict missing the current locale, the instance reads the text the dict leads it to: `load()` reads what the row holds.
