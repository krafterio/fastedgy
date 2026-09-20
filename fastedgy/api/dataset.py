# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException

from fastedgy.api_route_model.actions.patch_action import patch_item_fields
from fastedgy.api_route_model.exception import handle_action_exception
from fastedgy.api_route_model.registry import RouteModelRegistry, TypeModel
from fastedgy.dependencies import Inject
from fastedgy.http import Request
from fastedgy.i18n import _t
from fastedgy.metadata_model import MetadataModelRegistry, TypeMapMetadataModels
from fastedgy.metadata_model.generator import (
    generate_class_name,
    generate_metadata_name,
    resolve_synchronizable_mode,
)
from fastedgy.models.base import BaseModel
from fastedgy.orm import Registry
from fastedgy.orm.access_guard import AccessDeniedError, ModelAction, acheck_access
from fastedgy.orm.transaction import with_transaction
from fastedgy.schemas.dataset import Resequence, ResequenceRequest, SyncState, SyncStateItem

# One router per route, so an app can mount them under different prefixes:
# workspace extra fields make the metadata tenant-specific, while resequencing
# stays wherever the app needs it. [router] mounts both, as before.
metadatas_router = APIRouter(prefix="/dataset", tags=["dataset"])
resequence_router = APIRouter(prefix="/dataset", tags=["dataset"])
sync_state_router = APIRouter(prefix="/dataset", tags=["dataset"])


@metadatas_router.get("/metadatas")
async def get_metadata_models(
    meta_registry: MetadataModelRegistry = Inject(MetadataModelRegistry),
) -> TypeMapMetadataModels:
    return await meta_registry.get_map_models()


@sync_state_router.get("/sync-state")
async def get_sync_state(
    models: str | None = None,
    registry: RouteModelRegistry = Inject(RouteModelRegistry),
) -> SyncState:
    """How much each replicated model holds, so a client can skip what has not moved.

    An offline client mirrors a model by walking its manifest, which costs a
    request per page even when nothing changed. This answers the same question
    in one request for every model at once: how many records the caller can
    read, and when the freshest one was written. A client whose own numbers
    match has nothing to pull.

    Nothing is stored per device: both numbers are read live, through the
    model's own query, so the workspace scope, the ``@global_filter`` rules and
    the row-level guards apply exactly as they do on the list route. A model
    the caller cannot read is left out of the answer rather than refused: the
    others still have to be told.
    """
    requested = {name.strip() for name in models.split(",") if name.strip()} if models else None
    items: list[SyncStateItem] = []

    for model_cls in registry.get_registered_models():
        mode = resolve_synchronizable_mode(model_cls)

        if mode == "none":
            continue

        name = generate_metadata_name(model_cls)

        if requested is not None and name not in requested:
            continue

        try:
            await acheck_access(model_cls, ModelAction.read)
        except AccessDeniedError:
            continue

        items.append(
            SyncStateItem(
                model=name,
                mode=mode,
                count=await model_cls.query.count(),
                updated_at=await _freshest(model_cls),
            )
        )

    items.sort(key=lambda item: item.model)

    return SyncState(items=items)


async def _freshest(model_cls: TypeModel) -> datetime | None:
    """The `updated_at` of the freshest record the caller can read, if any.

    Read through the scoped query rather than an aggregate select, so a record
    the caller cannot see cannot date the model for them.
    """
    if "updated_at" not in model_cls.meta.fields:
        return None

    values = await model_cls.query.order_by("-updated_at").limit(1).values_list("updated_at", flat=True)

    return values[0] if values else None


@resequence_router.put("/resequence")
async def resequence(
    data: ResequenceRequest,
    request: Request,
    meta_registry: MetadataModelRegistry = Inject(MetadataModelRegistry),
    registry: Registry = Inject(Registry),
) -> Resequence:
    if not await meta_registry.is_registered(data.model_name):
        raise HTTPException(status_code=400, detail=_t("Model {model_name} not found", model_name=data.model_name))

    model_class_name = generate_class_name(data.model_name)
    model_class = cast(type[BaseModel], registry.get_model(model_class_name))
    records = []

    if data.ids:
        group_update = _prepare_group_update(model_class, data.group_field, data.group_value)

        sequence_update = _prepare_sequence_update(model_class, data.sequence_field, data.sequence_offset)

        if not group_update and not sequence_update:
            raise HTTPException(
                status_code=400,
                detail=_t("No action requested. Please provide group_field or sequence_field for resequencing"),
            )

        # Each record is written through the model's PATCH route: the same
        # fields, the same access rules and the same transformers.
        async def _apply_resequence() -> list[dict[str, Any]]:
            existing_records = await model_class.query.filter(model_class.columns.id.in_(data.ids)).all()

            if len(existing_records) != len(data.ids):
                raise HTTPException(status_code=400, detail=_t("Some IDs in the target list do not exist"))

            updated_records: list[dict[str, Any]] = []

            for sequence_index, record_id in enumerate(data.ids):
                values: dict[str, Any] = {}

                if group_update:
                    values[str(group_update["field"])] = group_update["value"]

                if sequence_update:
                    values[sequence_update["field"]] = sequence_update["offset"] + sequence_index

                await patch_item_fields(request, model_class, record_id, values)
                updated_records.append({"id": record_id, **values})

            return updated_records

        try:
            records = await with_transaction(_apply_resequence)
        except Exception as e:
            handle_action_exception(e, model_class)

    return Resequence(
        model_name=data.model_name,
        sequence_field=data.sequence_field,
        sequence_offset=data.sequence_offset,
        group_field=data.group_field,
        group_value=data.group_value,
        records=records,
    )


def _prepare_group_update(
    model_class: Any, group_field: str | None, group_value: Any | None
) -> dict[str, Any | None] | None:
    """Prepare data for group change"""
    if not group_field and group_value is None:
        return None

    if not group_field:
        raise HTTPException(status_code=400, detail=_t("group_field is required"))

    if group_field not in model_class.meta.fields:
        raise HTTPException(status_code=400, detail=_t("Field {field_name} not found on model", field_name=group_field))

    return {"field": group_field, "value": group_value}


def _prepare_sequence_update(
    model_class: Any, sequence_field: str | None, sequence_offset: int
) -> dict[str, Any] | None:
    """Prepare data for resequencing"""
    if not sequence_field:
        return None

    if sequence_field not in model_class.meta.fields:
        raise HTTPException(
            status_code=400, detail=_t("Field {field_name} not found on model", field_name=sequence_field)
        )

    return {
        "field": sequence_field,
        "offset": sequence_offset,
    }


router = APIRouter()
router.include_router(metadatas_router)
router.include_router(resequence_router)
router.include_router(sync_state_router)


__all__ = [
    "metadatas_router",
    "resequence_router",
    "router",
    "sync_state_router",
]
