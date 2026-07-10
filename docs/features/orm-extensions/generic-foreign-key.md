# Generic Foreign Key

`GenericForeignKey` is a polymorphic many-to-one relation: a single field that can point to a record of any allowed target model. It is stored as two sibling columns injected on the owner model — the target model name and the target primary key — while the field itself stays the only API surface.

Typical use cases: reminders, comments, attachments or activity logs attached to heterogeneous records.

```python
from fastedgy.orm import fields
from fastedgy.models.base import BaseModel


class Reminder(BaseModel):
    class Meta:
        tablename = "reminders"

    record = fields.GenericForeignKey(
        to=["Task", "CalendarEvent"],
        related_name="reminders",
        label=_t('Record'),
    )
```

This declaration injects two columns on the table (`record_model` and `record_id` by default), installs a `reminders` reverse relation on every target model, and wires the whole ecosystem: generated API payloads, query builder, fields selector, OpenAPI schemas and metadata.

## Options

| Option | Default | Description |
|---|---|---|
| `to` | — | Allowed targets: an iterable of model classes or class names, or a **callable** returning one. A callable is resolved lazily and never frozen, so it can be backed by an application registry filled at import time. |
| `related_name` | `None` | Installs a reverse to-many relation under this name on **every** target model. Omit it for a one-way relation (same contract as `ForeignKey`). |
| `model_column` | `<name>_model` | Physical column holding the target model name. Overridable so an existing schema can adopt the field without renaming. |
| `id_column` | `<name>_id` | Physical column holding the target id. |
| `model_field_kwargs` / `id_field_kwargs` | `{}` | Extra kwargs forwarded to the injected column fields (e.g. `{"max_length": 255}`, labels). |
| `expose_columns` | `"none"` | Backward-compatibility surface of the physical columns: `"none"`, `"read"` or `"write"` (see below). |
| `null` | `False` | Whether the relation is optional. Drives the nullability of both injected columns. |

The target model name is the snake_case form of the class name (`CalendarEvent` → `calendar_event`).

## Reading and writing (ORM)

Reading is asynchronous and cached per instance:

```python
reminder = await Reminder.query.get(id=42)
record = await reminder.record  # Task | CalendarEvent | None
```

Writing accepts a saved target instance, a `{"model": ..., "id": ...}` mapping or `None` (when nullable). Both sibling columns stay directly addressable:

```python
reminder.record = task           # fills record_model="task", record_id=task.id
reminder.record = {"model": "calendar_event", "id": 7}
reminder.record = None           # clears the pair (nullable relations only)

reminder.record_model            # "task"
reminder.record_id               # 12
```

Target records load through `target_cls.query`, so global filters and access guards fully apply: a target the current context is denied to read resolves to `None` instead of propagating the denial.

## Reverse relations

With `related_name`, every target model exposes a standard to-many accessor:

```python
await task.reminders.all()
await task.reminders.filter(is_sent=False).count()
await task.reminders.add(reminder)     # fills the generic pair and saves
await task.reminders.remove(reminder)  # clears the pair (nullable relations only)
```

The reverse relation behaves like a native one-to-many everywhere: fields selector (`task.reminders.remind_at`), query builder reverse paths (`R("reminders.remind_at", ...)` resolves through an EXISTS join on the pair) and nested payload operations.

## Generated API payloads

The reference itself is written as a `{"model": ..., "id": ...}` object:

```json
POST /api/reminders
{"record": {"model": "task", "id": 42}, "remind_at": "2026-07-20T10:00:00+02:00"}
```

An unknown or disallowed model is rejected with a 422. When the relation is required, the reference must be provided on create.

Through the reverse relation, children support the full nested operations set on the parent payloads:

```json
POST /api/tasks
{"name": "With reminders", "reminders": [["create", {"remind_at": "..."}]]}

PATCH /api/tasks/42
{"reminders": [["create", {...}], ["update", {"id": 7, ...}], ["link", 8], ["delete", 9], ["set", [7]], ["clear"]]}
```

`create` and `update` fill the generic pair from the parent. On a required reference, `unlink` is rejected (400) and `delete`/`clear`/`set` delete the dropped children instead of writing `NULL` into the pair.

## Filtering

The physical columns are hidden by default: filters go through the field name and two virtual paths.

```json
["record", "=", ["task", 42]]
["record", "in", [["task", 42], ["calendar_event", 7]]]
["record", "is empty"]

["&", [["record.$model", "=", "task"], ["record.id", "in", [42, 50, 70]]]]
```

Reference values are strict `[model, id]` tuples — `{"model": ..., "id": ...}` objects are rejected. `<field>.$model` resolves on the model column and `<field>.id` on the id column, with the operators of the underlying column types.

## Fields selector

The serialized target is selected through the field name; the `$model` key discriminates the target model:

```
X-Fields: name,record.$model,record.name,record.emoji
```

```json
{"name": "...", "record": {"$model": "task", "id": 42, "name": "...", "emoji": "..."}}
```

Sub-fields under the reference are not statically validated (each target has its own fields): a requested field missing on a target is simply omitted. List serialization batch-loads the references — one query per (field, target model) over the whole page.

## Exposing the physical columns

By default the pair is a storage detail: hidden from schemas, inputs, metadata and public filters. `expose_columns` keeps it public for backward compatibility with deployed clients:

- `"read"` — the columns are serialized in responses and filterable, but rejected in writes.
- `"write"` — the columns are also accepted in input payloads, always as a **full pair** (both set, or both null when the relation is nullable), exclusive with the reference object, and validated against the allowed targets. The reference field itself becomes optional in the create input: the action requires one of the two forms.

```python
record = fields.GenericForeignKey(
    to=remindable_models,
    model_column="model_name",
    id_column="record_id",
    expose_columns="write",
)
```

## OpenAPI and metadata

- Output schema: `anyOf[$ref TargetA, $ref TargetB, partial object, null]` — the partial object documents the injected `$model` key with an enum of the allowed model names.
- Input schema: a shared `ReferenceObject` (`{model, id}`) with the allowed models in the field description.
- Metadata: the field is typed `reference` with a `targets` list; the reverse relation appears as a standard `one2many` on each target.

## Migrations

The injected columns are plain SQL types emitted through the standard Alembic autogenerate — no custom renderer. Mapping the field onto existing columns (`model_column`/`id_column` + matching kwargs) produces a zero-drift migration. There is no database-level foreign key across targets: cascade cleanup stays an application concern (signals on the target models).
