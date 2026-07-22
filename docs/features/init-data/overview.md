# Init Data - Overview

FastEdgy provides an init-data loader to seed reference data declaratively and idempotently. Records are described in plain Python files and identified by **stable external IDs**, so running the loader again updates existing rows instead of creating duplicates. The approach mirrors Odoo's `ir.model.data` pattern.

## Key features

- **Declarative data files**: One file per model under the server `data/` directory, exposing a `data` list of records
- **Stable external IDs**: Each record is tagged with `id("my_key")`, decoupling seed data from auto-incremented primary keys
- **Idempotent upsert**: Re-running compares the stored record and only creates or updates what changed
- **Relation resolution**: `ref("my_key")` wires foreign keys, one-to-many and many-to-many relations across files
- **File uploads**: `file("path")` uploads an asset through the Storage service and stores the resulting path
- **Automatic ordering**: Dependencies expressed with `ref(...)` are topologically sorted, even across files
- **CLI and programmatic**: Run via `db init-data` or call `load_data()` from code and tests

## How it works

1. **Discovery**: Every `*.py` file in the `data/` directory is loaded; the file name matches a model (its table name or metadata name). Files starting with `_` are ignored, so you can keep helper modules alongside data files.
2. **Parsing**: Each file exposes a `data` list of dictionaries. Every record declares its external key through the `id("...")` marker.
3. **Ordering**: Records referencing other records via `ref("...")` are topologically sorted so dependencies load first. A circular reference raises a clear error.
4. **Upsert**: For each record, the loader looks up its external key in the registry. If the target row still exists, scalar fields are compared and saved only when they changed; otherwise a new row is created. Relations are reconciled by diffing the current and target sets.
5. **Transaction**: The whole load runs inside a single transaction, so a failure leaves the database untouched.

## External ID registry

External keys are persisted in a dedicated `data_records` table (backed by the `DataRecord` model). Each entry maps a `key` to its target `model` and `record_id`. This registry is what makes the loader idempotent and lets `ref("...")` resolve to real primary keys across separate runs.

The `DataRecord` model ships with the framework and is registered automatically, so it appears in your migrations without any manual declaration.

[Usage Guide](guide.md){ .md-button .md-button--primary }
