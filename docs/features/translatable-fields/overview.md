# Translatable fields

A text field declared `translatable=True` keeps one value per locale. Your code reads and writes it as a plain string: the locale of the context (the request, the queued task, a `with context.locale(...)` block) decides which translation it reads and which one it writes.

```python
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


class Product(BaseModel):
    name = fields.CharField(max_length=200, translatable=True)
```

## Why use it

- **No translation tables**: no `product_translation` model, no join, no per-locale columns. A record stays one row.
- **Transparent**: the field is still a `str` for Python, Pydantic and OpenAPI. Routes, filters, ordering and exports need no change.
- **Resolved in SQL**: a read selects only the text of the current locale. The full document of translations never leaves the database.
- **Always something to read**: a locale without a translation reads the fallback locale's.

## Key features

- Option on `CharField`, `TextField`, `RichTextField` and `HTMLField`
- Stored as `jsonb`: `{"en": "Chair", "fr": "Chaise"}`
- Locale from the `Accept-Language` header, a queued task, or a `with context.locale(...)` block
- Writes merge into the stored document: a locale is set without touching the others
- A dict keyed by locale writes several locales at once, in Python as in a JSON body, described by the OpenAPI schema
- `_ts("...")` writes every locale at once, from your translation catalogs
- A read falls back from `fr-CA` to `fr`, then to the fallback locale, then to the first text
- `GET /{id}/translations` answers every locale of a record, and the metadata lists the locales
- Exports and imports hold one column per locale (`name:fr`, `Name (fr)`)
- Filters, the query builder, ordering and relation paths compare the text of the current locale
- Full-text search vectors built per locale, with the fallback
- `duplicate()` copies every translation
- Field metadata says which fields are translatable
- Alembic autogenerate converts existing data when a field turns translatable, and back, and `op.fill_translatable_fallback` follows a change of fallback locale

## Quick example

```python
from fastedgy import context

product = await Product.query.create(name="Chair")  # {"en": "Chair"}

with context.locale("fr"):
    product.name = "Chaise"
    await product.save()  # {"en": "Chair", "fr": "Chaise"}

    await Product.query.filter(name="Chaise").count()  # 1

with context.locale("de"):
    (await Product.query.get(id=product.id)).name  # "Chair", the fallback
```

[Usage Guide](guide.md){ .md-button .md-button--primary }
[Technical Details](technical.md){ .md-button }
