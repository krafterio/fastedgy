# Translatable fields - Usage guide

## Declare a translatable field

Add `translatable=True` to a `CharField`, a `TextField`, a `RichTextField` or an `HTMLField`. Every other option keeps its meaning: `max_length` and `min_length` apply to each translation.

```python title="models/product.py"
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


class Product(BaseModel):
    reference = fields.CharField(max_length=20)
    name = fields.CharField(max_length=200, translatable=True)
    description = fields.TextField(null=True, translatable=True)
    content = fields.RichTextField(null=True, translatable=True)

    class Meta(BaseModel.Meta):
        tablename = "products"
```

The column is a `jsonb` document holding one text per locale. Generate the migration as usual (see [Migrate an existing field](#migrate-an-existing-field)).

## Configure the locales

The locales come from the i18n settings:

```bash title=".env"
FALLBACK_LOCALE=en
AVAILABLE_LOCALES=["en","fr","de"]
```

- `fallback_locale` is the locale every record always has a text in, and the one a locale without a translation reads.
- `available_locales` is what the `Accept-Language` header can select, the locales a write accepts, and the locales `_ts()` writes. A regional locale (`fr-CA`) sits beside its language (`fr`).

## Choose the locale

The field reads and writes in the locale of the context, resolved in this order:

1. A `with context.locale("fr"):` block
2. The request, from its `Accept-Language` header (see [Internationalization](../i18n/overview.md))
3. The queued task, which runs in the locale it was enqueued in
4. The fallback locale

```python
from fastedgy import context

with context.locale("fr"):
    product = await Product.query.get(id=product_id)
    product.name = "Chaise"
    await product.save()
```

Outside a request, in a command for instance, `context.set_locale("fr")` sets the locale for the rest of the context.

## Read

A read answers the first text it finds, in this order:

1. The current locale, `fr-CA`
2. Its language, `fr`
3. The fallback locale
4. Each available locale, in the order of `available_locales`: only a record written before the fallback changed lacks the fallback
5. The text of its only locale, when the record holds a single one outside them

It is `None` when the record holds no text at all, or several texts and none of these locales.

```python
product = await Product.query.create(name="Chair")

with context.locale("fr"):
    (await Product.query.get(id=product.id)).name  # "Chair"
```

## Write

A string sets the text of the current locale and leaves the other locales as they are:

```python
product = await Product.query.create(name="Chair")  # {"en": "Chair"}

with context.locale("fr"):
    await product.update(name="Chaise")  # {"en": "Chair", "fr": "Chaise"}

with context.locale("de"):
    await product.update(name="Stuhl")  # {"en": "Chair", "fr": "Chaise", "de": "Stuhl"}
```

The rules every write follows, whether it comes from `save()`, `update()`, `QuerySet.update()`, `bulk_create()` or `bulk_update()`:

- **The fallback is filled**: a record created in `fr` gets its text in the fallback locale too, `{"en": "Chaise", "fr": "Chaise"}`, so every locale reads something.
- **Rewriting what a locale reads changes nothing**: a record read in `fr` through the fallback, then saved for another field, does not turn the fallback text into a French translation.
- **`None` removes the locale**: the other locales keep their text. A document left without any locale is `NULL`.
- **Only the available locales**: a write in a locale outside `available_locales` (and the fallback) raises a `ValueError`.

### Write several locales

A dict keyed by locale sets each locale it names, with the same rules: the others keep their text, `None` removes one, and the fallback is filled from the first text when the record has none yet.

```python
product = await Product.query.create(name={"en": "Chair", "fr": "Chaise"})

await product.update(name={"de": "Stuhl", "fr": None})  # {"en": "Chair", "de": "Stuhl"}
```

Each text is validated as a plain value would be (`max_length`, `min_length`, `pattern`), the keys must be available locales, and a field that is not `null=True` refuses `None` for its fallback locale. A record created with such a field takes a text in one locale at least: `{}` or `{"de": None}` raises a `ValueError`, a `422` through the API. Until it is saved, the attribute holds the dict; once saved, it reads the text of the current locale.

### Write every locale from the catalogs

A message marked with `_ts()` writes its translation in every available locale, read from your `.po` catalogs. Only the locales the message is translated in are stored, the fallback always:

```python
from fastedgy.i18n import _ts

category = await Category.query.create(name=_ts("Furniture"))
# {"en": "Furniture", "fr": "Meubles", "de": "Möbel"}
```

On an existing record, `_ts()` replaces the whole document. In init data files, it keeps the records in line with the catalogs: a record is updated when its translations differ from what the catalogs give.

```python title="data/category.py"
from fastedgy.i18n import _ts
from fastedgy.orm.loader import id

data = [
    {"id": id("category_furniture"), "name": _ts("Furniture")},
    {"id": id("category_lighting"), "name": {"en": "Lighting", "fr": "Luminaires"}},
]
```

A dict of locales updates the record when one of the locales it names holds another text.

### Read every translation

`read_translations()` returns the document a stored record holds, every locale at once, and `fetch_translations()` those of many records in one statement:

```python
from fastedgy.orm.fields import fetch_translations, read_translations

await read_translations(product, "name")  # {"en": "Chair", "fr": "Chaise"}
await fetch_translations(Product, [1, 2])  # {1: {"name": {...}, "description": {...}}, 2: {...}}
```

## Query

Filters compare the text of the current locale, the fallback's when it has none. Every text operator works, with keyword lookups as with the query builder:

```python
from fastedgy.orm.filter import R

with context.locale("fr"):
    await Product.query.filter(name="Chaise").all()
    await Product.query.filter(name__icontains="chai").all()
    await Product.query.filter(R("name", "starts with", "Ch")).all()
    await Category.query.filter(R("products.name", "=", "Chaise")).all()
```

Ordering follows the same text, on the field itself or through a relation:

```python
with context.locale("fr"):
    await Product.query.order_by("name").all()
    await Category.query.order_by("products__name").all()
```

A SQL function you call yourself on the column needs the text spelled out with `translated()`:

```python
from sqlalchemy import func

from fastedgy.orm.fields import translated

longest = func.max(func.length(translated(Product.table.columns.name)))
```

## API

The routes of an `@api_route_model` need nothing more. A request reads and writes in the language of its `Accept-Language` header:

```bash
curl -X PATCH /api/products/1 -H "Accept-Language: fr" -d '{"name": "Chaise"}'
curl /api/products/1 -H "Accept-Language: fr"   # "name": "Chaise"
curl /api/products/1                            # "name": "Chair"
```

A create or a patch also takes the translations keyed by locale, whatever the language of the request:

```bash
curl -X PATCH /api/products/1 -d '{"name": {"en": "Chair", "fr": "Chaise", "de": "Stuhl"}}'
```

A locale outside `available_locales`, or a text breaking the constraints of the field, answers `422`. The OpenAPI schema says it: the field reads as a `string`, and the create and update bodies take a `string` or an object whose keys are the available locales:

```json
{
  "anyOf": [
    {"maxLength": 200, "type": "string"},
    {
      "additionalProperties": {"anyOf": [{"maxLength": 200, "type": "string"}, {"type": "null"}]},
      "propertyNames": {"enum": ["en", "fr", "de"]},
      "type": "object"
    }
  ]
}
```

### Read every translation of a record

Every model holding a translatable field gets a route answering all its translations, typed in OpenAPI as `<Model>-Translations`:

```bash
curl /api/products/1/translations
# {"name": {"en": "Chair", "fr": "Chaise"}, "description": {}}
```

It reads the record through the same scoping as `GET /api/products/1`, and answers `404` when that one would. The translations go back through the regular patch, as an object keyed by locale.

### Metadata

The field metadata (`/api/dataset/metadatas`) carries `"translatable": true` and `"locales"`, the available locales with the fallback first, so a client knows to offer one input per language:

```json
{"name": "name", "type": "char", "translatable": true, "locales": ["en", "fr", "de"]}
```

## Export and import

A field selector naming a locale of a translatable field (`name:fr`) gives one column per locale, headed `Name (fr)`, in the exports and the import templates:

```bash
curl /api/products/export?format=xlsx -H "X-Fields: reference,name:en,name:fr,name:de"
curl /api/products/import/template?format=csv -H "X-Fields: reference,name:en,name:fr"
# Reference,Name (en),Name (fr)
```

An import reads those columns, by their label or as `name:fr`, as the translations keyed by locale: an empty cell leaves its locale as it is. A column of the field itself (`Name`) writes the locale of the request. A file holding both a column of the field itself and a column of one of its locales is refused with a `400`, either would overwrite the other.

## Full-text search

A translatable field is searchable like any text field. The vector of each locale reads the text a read in that locale gives, and a save recomputes the vectors of every locale.

## Duplicate a record

`duplicate()` copies every translation of the translatable fields, not only the current locale's. A field given in `values` keeps the value given.

## Migrate an existing field

Turning a field translatable, or turning it back, changes its column type. `fastedgy db makemigrations` detects it and writes the conversion of the stored values:

```python
def upgrade():
    op.convert_to_translatable("products", "name", fallback_locale="en", existing_type=sa.VARCHAR(length=200))


def downgrade():
    op.convert_from_translatable("products", "name", fallback_locale="en", type_=sa.VARCHAR(length=200))
```

- To translatable, each text becomes the text of the fallback locale: `"Chair"` becomes `{"en": "Chair"}`, `NULL` stays `NULL`.
- Back to text, the text of the fallback locale is kept and the other translations are dropped.

A hand-written migration can use the SQL helpers in its own `alter_column`:

```python
from fastedgy.orm.migration import text_from_translatable, translatable_from_text

op.alter_column(
    "products",
    "name",
    type_=postgresql.JSONB(),
    postgresql_using=translatable_from_text("name", "en"),
)
```

Changing `max_length`, or moving between `CharField` and `TextField`, needs no migration: the column stays a `jsonb` document.

### Change the fallback locale

The fallback locale is a setting, no part of the schema: autogenerate cannot see it change. The records written before read their first available locale, in the order of `available_locales`, in a locale they lack: a migration giving each of them a text in the new fallback keeps the reads, the filters and the search in line:

```python
def upgrade():
    op.fill_translatable_fallback("products", "name", "fr", from_locale="en")
```

Each record without a text in `fr` takes its `en` one; a record holding neither stays as it is. One call per translatable column.

## Best practices

- **Keep the fallback locale stable**, and fill the new one in a migration when it changes.
- **Seed with `_ts()`**: reference data then follows your catalogs on every `init-data` run.
