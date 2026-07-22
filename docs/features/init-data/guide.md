# Init Data - Usage Guide

This guide shows how to seed reference data with the FastEdgy init-data loader.

## Setup

Seed data lives in a `data/` directory next to your server code (resolved from the `server_path` setting, i.e. `{server_path}/data`).

The registry that makes the loader idempotent is stored in the `data_records` table. The `DataRecord` model is registered automatically, so a normal migration run picks it up:

```bash
fastedgy db makemigrations -m "Add data records table"
fastedgy db migrate
```

## Writing a data file

Create one file per model. The file name must match the model's table name (or its metadata name). Each file exposes a `data` list, and every record declares its external key with `id("...")`:

```python
# data/country.py
from fastedgy.orm.loader import id

data = [
    {"id": id("country_fr"), "code": "FR", "name": "France"},
    {"id": id("country_be"), "code": "BE", "name": "Belgium"},
]
```

The helpers are imported explicitly from `fastedgy.orm.loader` — only `id`, `ref` and `file` are markers interpreted by the loader; every other key is a normal model field.

## Relations with `ref()`

Use `ref("...")` to point at another record by its external key. It works for foreign keys as well as one-to-many and many-to-many relations:

```python
# data/state.py
from fastedgy.orm.loader import id, ref

data = [
    {"id": id("state_fr_75"), "country": ref("country_fr"), "code": "75", "name": "Paris"},
    {"id": id("state_fr_13"), "country": ref("country_fr"), "code": "13", "name": "Bouches-du-Rhône"},
]
```

For a collection relation, pass a list of references:

```python
# data/role.py
from fastedgy.orm.loader import id, ref

data = [
    {
        "id": id("role_admin"),
        "name": "Administrator",
        "permissions": [ref("perm_read"), ref("perm_write"), ref("perm_delete")],
    },
]
```

Many-to-many and one-to-many relations are reconciled by diff: references not present anymore are removed, and new ones are added. Existing links that still match are left untouched.

## Files with `file()`

Use `file("...")` to upload an asset into a field. The path is resolved relative to `server_path`, and `../` is allowed to reach files outside the server directory:

```python
# data/user.py
from fastedgy.orm.loader import file, id

data = [
    {
        "id": id("user_system"),
        "email": "system@example.io",
        "name": "System",
        "avatar": file("../app/assets/images/favicon.png"),
    },
]
```

The loader reads the file, uploads it through the Storage service (in the model's directory, using global storage when the model has no `workspace` field) and stores the returned path in the field. The upload happens once: on later runs, a field that already holds a value is left as is.

## Dependency ordering

Records are sorted so that every `ref(...)` target loads first, even when the dependency lives in another file. In the example above, `country.py` is always applied before `state.py` because each state references a country. You never manage the order manually; a circular reference is reported as an error.

## Running the loader

Run the CLI command to load (create or update) all data files:

```bash
fastedgy db init-data
```

The command prints how many records were created and updated:

```
Init data loaded: 103 created, 0 updated
```

Running it again is safe — unchanged records are skipped, so a second run typically reports `0 created, 0 updated`.

## Programmatic usage

The same entry point is available in code, which is handy for test fixtures that need a freshly seeded database:

```python
from fastedgy.orm.loader import load_data

async def seed():
    report = await load_data()
    print(report.created, report.updated)
```

Pass `data_dir` to load from a custom directory:

```python
await load_data(data_dir="/path/to/data")
```

## Best practices

- **Use descriptive external keys**: `country_fr`, `role_admin` — they are permanent identifiers, so keep them stable
- **One file per model**: Name it after the model's table name and keep records focused
- **Prefix helper modules with `_`**: Shared lists or constants in `_helpers.py` are ignored by the loader
- **Keep data files pure**: They should build the `data` list only, with no side effects
- **Prefer `ref()` over raw IDs**: Referencing by external key keeps seed data portable across environments

[Back to Overview](overview.md){ .md-button }
