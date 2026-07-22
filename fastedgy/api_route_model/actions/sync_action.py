# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Batch sync action: apply a client outbox in one transactional request.

Offline-first clients (flutter_fastedgy) buffer their writes while
disconnected and replay them on reconnect. This action lets them apply the
buffered updates/deletes of one model in a single request, resolving
conflicts server-side with a per-field three-way merge:

- each operation carries the ``base`` snapshot of the record as the client
  knew it; fields the server changed since that base conflict with the
  buffered ones;
- buffered fields disjoint from the server changes always apply (both writes
  survive);
- overlapping fields are resolved last-writer-wins (server ``updated_at`` vs
  the operation ``created_at``) and the patch is reduced accordingly;
- a delete loses to a fresher server write (the record is returned instead).

Creates are intentionally NOT handled here: they often carry model-specific
semantics (factories, side effects) and stay on their regular POST route.

The action is opt-in: enable it per model with
``@api_route_model(sync=True)``. Custom routes can reuse
:func:`sync_items_action` directly (like the other ``*_action`` helpers) and
pass a pre-scoped ``query`` to restrict the reachable records.

Allowed operations align with the model's route configuration: a model that
disables the ``patch`` (resp. ``delete``) action rejects ``update`` (resp.
``delete``) sync operations with a 403. Override with
``@api_route_model(sync={"ops": ["update"]})`` or the ``ops`` parameter of
:func:`sync_items_action` when a custom route needs a stricter policy.
"""

import json
from datetime import datetime
from typing import Any, Callable, Literal, Sequence, cast

from fastapi import APIRouter, Body, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from fastedgy.api_route_model.action import BaseApiRouteAction
from fastedgy.api_route_model.actions.delete_action import DeleteApiRouteAction, delete_item_action
from fastedgy.api_route_model.actions.patch_action import PatchApiRouteAction, patch_item_action
from fastedgy.api_route_model.registry import (
    CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN,
    RouteModelActionOptions,
    RouteModelOptions,
    RouteModelRegistry,
    TypeModel,
)
from fastedgy.dependencies import get_service
from fastedgy.i18n import _t
from fastedgy.api_route_model.types import ModelUpdate
from fastedgy.http import Request
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.orm import transaction
from fastedgy.orm.field_selector import filter_selected_fields
from fastedgy.orm.manager import BaseManager
from fastedgy.orm.query import QuerySet
from fastedgy.schemas import BaseModel as BaseSchema
from fastedgy.timezone import ensure_aware


class SyncOperation(BaseSchema):
    op: Literal["update", "delete"]
    id: int
    payload: dict[str, Any] | None = None
    base: dict[str, Any] | None = None
    created_at: datetime | None = None


class SyncOperationResult(BaseSchema):
    id: int
    status: Literal["applied", "merged", "conflict", "deleted"]
    record: dict[str, Any] | None = None
    applied_fields: list[str] | None = None
    discarded_fields: list[str] | None = None


class SyncApplyInput(BaseSchema):
    operations: list[SyncOperation]


class SyncApplyResult(BaseSchema):
    results: list[SyncOperationResult]


class SyncApiRouteAction(BaseApiRouteAction):
    """Action applying a batch of buffered offline writes (opt-in)."""

    name = "sync"

    default_options = False

    @classmethod
    def register_route(cls, router: APIRouter, model_cls: TypeModel, options: RouteModelActionOptions) -> None:
        """Register the sync route."""
        options = cast(RouteModelActionOptions, dict(options))
        ops = cast("Sequence[str] | None", options.pop("ops", None))

        router.add_api_route(
            **{
                "path": "/sync",
                "endpoint": generate_sync_items(model_cls, ops),
                "methods": ["POST"],
                "summary": f"Sync buffered {model_cls.__name__} writes",
                "description": (
                    f"Apply a batch of buffered offline {model_cls.__name__} updates/deletes "
                    "with per-field three-way merge conflict resolution"
                ),
                "response_model": SyncApplyResult,
                **options,
            }
        )


def generate_sync_items[M: BaseModel | BaseView](
    model_cls: type[M],
    ops: Sequence[str] | None = None,
) -> Callable[..., Any]:
    async def sync_items(
        request: Request,
        data: SyncApplyInput = Body(),
    ) -> Any:
        return await sync_items_action(request, model_cls, data.operations, ops=ops)

    return sync_items


@transaction
async def sync_items_action[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    operations: list[SyncOperation],
    query: QuerySet | BaseManager | None = None,
    ops: Sequence[str] | None = None,
) -> SyncApplyResult:
    allowed = tuple(ops) if ops is not None else allowed_sync_ops(model_cls)

    for operation in operations:
        if operation.op not in allowed:
            raise HTTPException(
                status_code=403,
                detail=_t(
                    "Sync operation '{op}' is not allowed for {model}", op=operation.op, model=model_cls.__name__
                ),
            )

    results = [await _apply(request, model_cls, operation, query) for operation in operations]

    return SyncApplyResult(results=results)


def allowed_sync_ops(model_cls: TypeModel) -> tuple[str, ...]:
    """The sync operations the model's route configuration allows.

    Aligns with the other generated actions: ``update`` requires the ``patch``
    action to be enabled, ``delete`` the ``delete`` action. An unregistered
    model falls back to the action defaults (both enabled).
    """
    options = _registered_actions_options(model_cls)
    ops: list[str] = []

    if PatchApiRouteAction.should_register(options):
        ops.append("update")

    if DeleteApiRouteAction.should_register(options):
        ops.append("delete")

    return tuple(ops)


def _registered_actions_options(model_cls: TypeModel) -> RouteModelOptions:
    for registry_ref in (RouteModelRegistry, CONSOLE_ROUTE_MODEL_REGISTRY_TOKEN):
        try:
            registry = get_service(registry_ref)
        except Exception:
            continue

        if registry.is_model_registered(model_cls):
            return cast(RouteModelOptions, registry.get_model_options(model_cls).get("actions", {}))

    return cast(RouteModelOptions, {})


async def _apply[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    operation: SyncOperation,
    query: QuerySet | BaseManager | None = None,
) -> SyncOperationResult:
    base_query = query if query is not None else model_cls.query  # type: ignore[attr-defined]
    item = await base_query.filter(id=operation.id).get_or_none()

    if item is None:
        return SyncOperationResult(
            id=operation.id,
            status="deleted" if operation.op == "update" else "applied",
        )

    current = await filter_selected_fields(item, None)

    if operation.op == "delete":
        if _server_is_newer(item, operation):
            return SyncOperationResult(id=operation.id, status="conflict", record=_jsonable(current))

        await delete_item_action(request, model_cls, operation.id, query)

        return SyncOperationResult(id=operation.id, status="applied")

    # Reduce to the PATCH schema surface (drops excluded/unknown fields) so
    # the merge and the reported applied_fields only cover real writes.
    writable = cast(Any, ModelUpdate[model_cls]).model_fields
    payload = {field: value for field, value in (operation.payload or {}).items() if field in writable}
    server_changed = set(payload) if operation.base is None else _changed_fields(model_cls, operation.base, current)
    conflicts = [field for field in payload if field in server_changed]

    if conflicts and _server_is_newer(item, operation):
        for field in conflicts:
            payload.pop(field, None)

        if not payload:
            return SyncOperationResult(
                id=operation.id,
                status="conflict",
                record=_jsonable(current),
                discarded_fields=conflicts,
            )

        record = await _patch(request, model_cls, operation.id, payload, query)

        return SyncOperationResult(
            id=operation.id,
            status="merged",
            record=_jsonable(record),
            applied_fields=sorted(payload),
            discarded_fields=conflicts,
        )

    record = await _patch(request, model_cls, operation.id, payload, query)

    return SyncOperationResult(
        id=operation.id,
        status="applied",
        record=_jsonable(record),
        applied_fields=sorted(payload),
    )


async def _patch[M: BaseModel | BaseView](
    request: Request,
    model_cls: type[M],
    item_id: int,
    payload: dict[str, Any],
    query: QuerySet | BaseManager | None = None,
) -> dict[str, Any]:
    try:
        item_data = cast(Any, ModelUpdate[model_cls])(**payload)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error

    result = await patch_item_action(request, model_cls, item_id, item_data, query)

    if isinstance(result, dict):
        return result

    return await filter_selected_fields(cast(Any, result), None)


def _changed_fields[M: BaseModel | BaseView](
    model_cls: type[M],
    base: dict[str, Any],
    current: dict[str, Any],
) -> set[str]:
    fields = (set(base) | set(current)) - _server_managed_fields(model_cls)

    return {
        field
        for field in fields
        if json.dumps(base.get(field), sort_keys=True, default=str)
        != json.dumps(current.get(field), sort_keys=True, default=str)
    }


def _server_managed_fields(model_cls: type[BaseModel | BaseView]) -> set[str]:
    fields: dict[str, Any] = getattr(model_cls.meta, "fields", {})

    return {
        name
        for name, field in fields.items()
        if getattr(field, "primary_key", False)
        or getattr(field, "read_only", False)
        or getattr(field, "auto_now", False)
        or getattr(field, "auto_now_add", False)
    }


def _server_is_newer(item: BaseModel | BaseView, operation: SyncOperation) -> bool:
    updated_at = getattr(item, "updated_at", None)

    if updated_at is None or operation.created_at is None:
        return False

    return ensure_aware(updated_at) > ensure_aware(operation.created_at)


def _jsonable(record: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(record, default=str))


__all__ = [
    "SyncApiRouteAction",
    "allowed_sync_ops",
    "SyncOperation",
    "SyncOperationResult",
    "SyncApplyInput",
    "SyncApplyResult",
    "sync_items_action",
]
