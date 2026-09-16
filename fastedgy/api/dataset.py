# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, cast

from fastapi import APIRouter, HTTPException

from fastedgy.api_route_model.actions.patch_action import patch_item_fields
from fastedgy.api_route_model.exception import handle_action_exception
from fastedgy.dependencies import Inject
from fastedgy.http import Request
from fastedgy.i18n import _t
from fastedgy.metadata_model import MetadataModelRegistry, TypeMapMetadataModels
from fastedgy.metadata_model.generator import generate_class_name
from fastedgy.models.base import BaseModel
from fastedgy.orm import Registry
from fastedgy.orm.transaction import with_transaction
from fastedgy.schemas.dataset import Resequence, ResequenceRequest

# One router per route, so an app can mount them under different prefixes:
# workspace extra fields make the metadata tenant-specific, while resequencing
# stays wherever the app needs it. [router] mounts both, as before.
metadatas_router = APIRouter(prefix="/dataset", tags=["dataset"])
resequence_router = APIRouter(prefix="/dataset", tags=["dataset"])


@metadatas_router.get("/metadatas")
async def get_metadata_models(
    meta_registry: MetadataModelRegistry = Inject(MetadataModelRegistry),
) -> TypeMapMetadataModels:
    return await meta_registry.get_map_models()


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


__all__ = [
    "metadatas_router",
    "resequence_router",
    "router",
]
