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
SELECT coalesce(
  products.name ->> $1,  -- the locale, fr-CA
  products.name ->> $2,  -- its language, fr
  products.name ->> $3,  -- the fallback locale
  (SELECT products.name ->> _available.locale
     FROM unnest($4) WITH ORDINALITY AS _available(locale, position)
    WHERE products.name ? _available.locale
    ORDER BY _available.position LIMIT 1),  -- the first available locale it holds
  jsonb_path_query_first(jsonb_path_query_array(products.name, '$.*'), 'strict $ ? (@.size() == 1)') ->> 0
                         -- the text of its only locale
) AS name FROM products
```

The locales are bound parameters resolved on every execution, not compiled into the SQL: the compiled statement is cached and shared by every locale, and by every list of available locales (`$4`, a `text[]` in the order of the settings). `coalesce` stops at the first text, so the subquery only runs on a document lacking the fallback, and the last resort on one holding no available locale either. It answers a document holding a single text, whichever its locale, and `NULL` for one holding several: the order of the keys of a `jsonb` document says nothing of the locales. The column's result processor is disabled, so the driver hands back the text as it is.

## Comparing and ordering

The comparator rewrites every operator applied to the column on the localized text, so `==`, `ilike`, `in_`, `is_`, `match`, `asc` and `desc` all compare the text a read returns. The ascending terms of `order_by()`, which Edgy passes as the bare column, and the aggregate ordering a record by a to-many relation are wrapped by `translated()` in `QuerySet._prepare_order_by` and `aggregated_relation_column`.

## Writing

The value bound for the column is a payload:

| Value | Payload |
|-------|---------|
| `str` or `None` | `{"read": [locale, language, fallback, text], "available": [locale, ...], "missing": {fallback: text}, "set": {locale: text}}` |
| `dict` | `{"missing": {fallback: first text}, "set": {locale: text, ...}}` |
| `TranslatableString` | `{"replace": true, "set": {locale: translation, ...}}` |

The locales of a `str` or a `dict` must be available ones: the bind raises a `ValueError` otherwise, the last check of a write that skipped validation (`update()`, `QuerySet.update()`).

`bind_expression` wraps it in a scalar subquery merging it into the current document, `NULL` on an insert:

```sql
SET name = (
  SELECT CASE
    WHEN _t.p ? 'read'
     AND coalesce(name ->> (_t.p -> 'read' ->> 0), name ->> (_t.p -> 'read' ->> 1),
                  name ->> (_t.p -> 'read' ->> 2),
                  <the first of _t.p -> 'available' the document holds>,
                  jsonb_path_query_first(jsonb_path_query_array(name, '$.*'), 'strict $ ? (@.size() == 1)') ->> 0)
         IS NOT DISTINCT FROM (_t.p -> 'read' ->> 3)
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

`build_tsvector_expression` reads a translatable source with the chain of a read in the locale of the vector, its locales as literals: `coalesce(col ->> 'fr', col ->> 'en', col ->> 'de', <the text of its only locale>)`, the available locales following the fallback. The save signal recomputes the vector of every available locale in one `UPDATE`, skipped when no vector changes: a write in one locale may fill the fallback, and every locale without a text of its own reads it.

## Migrations

`process_translatable_revision_directives` runs within `fastedgy_process_revision_directives`. On the upgrade and downgrade operations, it replaces the type change of an `alter_column`:

| From | To | Operation | `USING` |
|------|----|-----------|---------|
| `VARCHAR`, `TEXT` | `Translatable` | `convert_to_translatable` | `CASE WHEN col IS NULL THEN NULL ELSE jsonb_build_object('en', col) END` |
| `Translatable`, `JSONB` | `VARCHAR`, `TEXT` | `convert_from_translatable` | `col ->> 'en'` |

Alembic renders no `postgresql_using`, hence the operations of their own. The fallback locale is the one configured when the migration is generated. The rest of an `alter_column` (nullability, default, comment) stays in place after the conversion. A `Translatable` column compiles to `JSONB`, so a schema in line with the models produces no migration.

`fill_translatable_fallback(table, column, fallback_locale, from_locale)` is written by hand, the fallback being a setting:

```sql
UPDATE products SET name = name || jsonb_build_object('fr', name -> 'en')
WHERE name ? 'en' AND NOT name ? 'fr'
```

A document holding neither locale is left as it is.

## API

- `TranslationsApiRouteAction` registers `GET /{item_id}/translations` on a model holding a translatable field, nothing on any other. Its response model, built once per model, gives each translatable field as `dict[TranslationLocale, str]`. It runs the `PreLoadRecordViewTransformer`s, checks the record through the model's query, then reads the documents with `fetch_translations`.
- `MetadataField.locales` lists `available_locales()` for a translatable field: the fallback first, then the other available locales.
- The dataflow takes a locale as the converter of a translatable field (`expand_columns`, `column_label`, `translation_locale` in `fastedgy.dataflow.exporter`): an export reads the documents of the page with `fetch_translations`, an import gathers the columns of a field into its translations.

## Reference

| Name | Module | Description |
|------|--------|-------------|
| `Translatable` | `fastedgy.orm.fields` | Column type of a translatable field |
| `translated(column)` | `fastedgy.orm.fields` | The text of the current locale, any other column unchanged |
| `is_translatable(field)` | `fastedgy.orm.fields` | Whether a field is declared `translatable=True` |
| `read_translations(record, name)` | `fastedgy.orm.fields` | Every locale a stored record holds |
| `fetch_translations(model, keys, names=None)` | `fastedgy.orm.fields` | Every locale of many records, in one statement |
| `available_locales()` | `fastedgy.orm.fields` | The locales a write accepts, the fallback first |
| `language_of(locale)` | `fastedgy.orm.fields` | The language of a regional locale, `fr` for `fr-CA` |
| `translations_of(message)` | `fastedgy.orm.fields` | The translations a `_ts()` message writes |
| `context.locale(code)` | `fastedgy.context` | Read and write in a locale for a block |
| `translatable_from_text`, `text_from_translatable` | `fastedgy.orm.migration` | SQL of the conversions, for hand-written migrations |
| `op.fill_translatable_fallback(...)` | `fastedgy.orm.migration` | Give every record a text in a new fallback locale |

## Limits

- `distinct("name")` on a translatable field compares the stored documents, and cannot lead an `order_by("name")`.
- After an `update()` with a dict missing the current locale, the instance reads the text the dict leads it to: `load()` reads what the row holds.
