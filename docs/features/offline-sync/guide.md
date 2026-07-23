# Offline Sync - Usage Guide

This guide covers enabling the sync action, the request/response contract, how the three-way merge resolves conflicts, restricting operations, reusing the action in custom scoped routes, and the two write-protection primitives sync relies on (the relation guard and `read_only` fields).

## Enabling sync on a model

Sync is opt-in. Add it to the model's `api_route_model` decorator:

```python
from fastedgy.orm import fields
from fastedgy.models.base import BaseModel
from fastedgy.api_route_model import api_route_model


@api_route_model(sync=True)
class Product(BaseModel):
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
```

This adds one endpoint next to the standard CRUD routes:

```
POST /api/products/sync
```

Because sync only ever replays `update` and `delete` operations, it inherits the model's `patch` and `delete` permissions automatically — see [Allowed operations](#allowed-operations) below.

## Request and response

The endpoint accepts a batch of operations (max **500** per request) and returns one result per operation, in order.

### Request body

```json
{
  "operations": [
    {
      "op": "update",
      "id": 42,
      "payload": { "name": "New name", "price": "19.90" },
      "base": { "name": "Old name", "price": "24.90", "quantity": 3 },
      "created_at": "2026-07-22T09:15:00Z"
    },
    {
      "op": "delete",
      "id": 43,
      "created_at": "2026-07-22T09:16:00Z"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `op` | `"update"` \| `"delete"` | The buffered operation kind |
| `id` | `int` | Server id of the target record |
| `payload` | `object` \| `null` | Buffered field changes (update only); unknown/excluded fields are dropped |
| `base` | `object` \| `null` | The record as the client last knew it — the merge baseline |
| `created_at` | `datetime` \| `null` | Client write time — the last-writer-wins tie-breaker |

### Response body

```json
{
  "results": [
    {
      "id": 42,
      "status": "merged",
      "record": { "id": 42, "name": "New name", "price": "24.90", "quantity": 5 },
      "applied_fields": ["name"],
      "discarded_fields": ["price"]
    },
    {
      "id": 43,
      "status": "applied"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | `int` | The operation's target id (echoed) |
| `status` | enum | `applied` \| `merged` \| `conflict` \| `deleted` \| `rejected` — see the [statuses table](overview.md#operation-statuses) |
| `record` | `object` \| `null` | The resulting (or current, on `conflict`) server record |
| `applied_fields` | `string[]` \| `null` | Fields actually written (update) |
| `discarded_fields` | `string[]` \| `null` | Fields dropped because the server was fresher |
| `detail` | `string` \| `null` | Rejection reason (`rejected` only) |

## How the three-way merge works

For an `update`, sync compares three versions of each field: the client's `base` (what it started from), the server's `current` value, and the buffered `payload` value.

1. **Reduce to writable fields.** The payload is first reduced to the model's PATCH schema surface — unknown, excluded, [`read_only`](#read-only-fields), and server-managed fields are dropped, so the merge and `applied_fields` only ever cover real writes.
2. **Detect server changes.** A field is *server-changed* when `current` differs from `base`. Server-managed fields (`primary_key`, `read_only`, `auto_now`, `auto_now_add`) and to-many relations are excluded from this diff; to-one relations are compared by id only (the base and the server selection may carry different shapes for the same relation).
3. **Classify each payload field.**
    - **Disjoint** (server did not touch it) → always applied, regardless of clocks. Both sides' writes survive.
    - **Conflicting** (both touched it) → resolved below.
4. **Resolve conflicts.**
    - Fields declared with [`merge_blocks=True`](#block-text-merge) are merged line-by-line and drop out of the conflict set.
    - Remaining conflicts follow **last-writer-wins**: if the server is newer (`updated_at` > the operation `created_at`), those fields are discarded; otherwise the client value wins.

The resulting status:

- all payload applied → `applied`
- some applied, some discarded → `merged` (with `applied_fields` / `discarded_fields`)
- everything discarded → `conflict` (the current server `record` is returned)

!!! note "Without a `base` snapshot"
    If an operation carries no `base`, sync cannot tell which fields the client actually diverged on, so it treats the **whole payload** as conflicting and resolves it as a single last-writer-wins unit. Always send a `base` to get field-level merging.

### Delete resolution

A `delete` operation:

- succeeds (`applied`) when the record is unchanged since the client's snapshot, or already gone (idempotent);
- loses (`conflict`) when the server has a fresher write — the delete is refused and the current `record` is returned, so the client can decide whether to re-delete.

## Allowed operations

By default the sync operations a model accepts mirror its route configuration:

- `update` requires the `patch` action to be enabled,
- `delete` requires the `delete` action to be enabled.

So a model that disables deletion rejects buffered deletes with a `403`:

```python
@api_route_model(sync=True, delete=False)  # accepts "update" only
class Tag(BaseModel):
    name = fields.CharField(max_length=100)
```

Tighten the policy explicitly with the `ops` option, independently of the CRUD actions:

```python
@api_route_model(sync={"ops": ["update"]})  # never replay deletes, even if delete is enabled
class Product(BaseModel):
    ...
```

An operation outside the allowed set is refused for the whole batch with a `403`.

## Reusing sync in custom routes

Like the other generated actions, sync exposes a reusable function — `sync_items_action` — so a custom route can apply a batch against a **pre-scoped** queryset. This is the multi-tenant pattern: restrict the reachable records to the caller's scope and let sync merge within it.

```python
from fastapi import APIRouter, Depends
from fastedgy.http import Request
from fastedgy.api_route_model.actions.sync_action import (
    SyncApplyInput,
    SyncApplyResult,
    sync_items_action,
)

router = APIRouter()


@router.post("/{workspace}/products/sync", response_model=SyncApplyResult)
async def sync_products(
    request: Request,
    data: SyncApplyInput,
    workspace: Workspace = Depends(get_current_workspace),
) -> SyncApplyResult:
    # Only records inside the caller's workspace are reachable: an operation
    # targeting an id outside the scope resolves as "deleted"/"applied", never
    # leaking or mutating another tenant's data.
    query = Product.query.filter(workspace=workspace)

    return await sync_items_action(
        request,
        Product,
        data.operations,
        query=query,
        ops=("update",),  # optional per-route policy override
    )
```

`sync_items_action(request, model_cls, operations, query=None, ops=None)`:

- `query` — a `QuerySet`/manager scoping the records the batch may reach (defaults to the model's global query). Every lookup, patch and delete goes through it.
- `ops` — an explicit allow-list overriding the model's default (see [Allowed operations](#allowed-operations)).

The whole call runs in one transaction, with a savepoint per operation.

## Write-protection primitives

Sync applies client-supplied payloads, so the same guards that protect the regular write routes protect it too. Two primitives are worth knowing when a model exposes sync.

### The relation guard

A relation input in a payload cannot do to a *related* model what that model's own API forbids. When the related model is registered in the `api_route_model` registry, its action configuration governs the record-mutating operations reachable through the relation:

- a nested **create** requires the related model's `create` action,
- a nested **update** requires its `patch` action,
- a nested **delete** requires its `delete` action.

Link-level operations (`link`/`unlink`/`set`/`clear`) belong to the owning side. On a to-many reverse relation (O2M / generic) they re-point the foreign key stored on the *target* records, so they count as an `update` of the target and are gated by its `patch` action; many-to-many links only touch the through table and stay free. Unregistered related models keep the historical behavior (child records managed through their parent).

A forbidden relation operation raises a `403` — on the regular routes and inside a sync batch alike. This guard is automatic; there is nothing to enable.

### Read-only fields

Fields that must never be set from an API input (a platform role, an immutable owner) are declared `read_only=True`. They are excluded from the generated input schemas, so no `POST`/`PATCH`/sync payload can write them — sync's field reduction drops them before the merge.

To set such a field from server code, use [`BaseModel.apply_readonly_values(...)`](../orm-extensions/models.md#read-only-fields), the explicit code-side escape hatch. See the [Models](../orm-extensions/models.md#read-only-fields) reference for details.

## Block text merge

Long-text fields lose data under plain last-writer-wins: two people editing different paragraphs would clobber each other. Declare such a field with `merge_blocks=True` and sync resolves its conflicts with a three-way, line-based merge (diff3) instead:

```python
@api_route_model(sync=True)
class Product(BaseModel):
    name = fields.CharField(max_length=200)
    description = fields.TextField(null=True, merge_blocks=True)
```

Both sides edit from the same `base`:

- hunks touching **disjoint** line ranges all survive (both edits kept);
- **overlapping** hunks fall back to last-writer-wins on that hunk (the fresher side wins).

A field merged this way drops out of the conflict set, so it is reported in `applied_fields` rather than `discarded_fields`. Only string values with a string `base` and `current` are merged; anything else falls back to standard field-level resolution.

The merge is exposed directly as `fastedgy.text_merge.merge_text_blocks(base, server, client, prefer_client)` if you need it outside sync.

[Back to Overview](overview.md){ .md-button }
