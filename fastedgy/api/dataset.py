# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, cast
from fastapi import APIRouter, HTTPException

from fastedgy.dependencies import Inject
from fastedgy.metadata_model import MetadataModelRegistry, TypeMapMetadataModels
from fastedgy.metadata_model.generator import generate_class_name
from fastedgy.orm import Model, Registry
from fastedgy.schemas.dataset import ResequenceRequest, Resequence

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("/metadatas")
async def get_metadata_models(
    meta_registry: MetadataModelRegistry = Inject(MetadataModelRegistry),
) -> TypeMapMetadataModels:
    return await meta_registry.get_map_models()


@router.put("/resequence")
async def resequence(
    data: ResequenceRequest,
    meta_registry: MetadataModelRegistry = Inject(MetadataModelRegistry),
    registry: Registry = Inject(Registry),
) -> Resequence:
    if not meta_registry.is_registered(data.model_name):
        raise HTTPException(
            status_code=400, detail=f"Model '{data.model_name}' not found"
        )

    model_class_name = generate_class_name(data.model_name)
    model_class = cast(type[Model], registry.get_model(model_class_name))
    records = []

    if data.ids:
        group_update = _prepare_group_update(
            model_class, data.group_field, data.group_value
        )

        sequence_update = _prepare_sequence_update(
            model_class, data.sequence_field, data.sequence_offset
        )

        if not group_update and not sequence_update:
            raise HTTPException(
                status_code=400,
                detail="No action requested. Please provide group_field or sequence_field for resequencing",
            )

        existing_records = await model_class.query.filter( # type: ignore
            model_class.columns.id.in_(data.ids)
        ).all()

        if len(existing_records) != len(data.ids):
            raise HTTPException(
                status_code=400, detail="Some IDs in the target list do not exist"
            )

        async with model_class.query.database.transaction(): # type: ignore
            records_by_id = {record.id: record for record in existing_records}
            sequence_index = 0

            for record_id in data.ids:
                record = records_by_id[record_id]
                updated_fields: dict[str, Any] = {"id": record_id}

                if group_update:
                    field_name = str(group_update["field"])
                    field_value = group_update["value"]
                    setattr(record, field_name, field_value)
                    updated_fields[field_name] = field_value

                if sequence_update:
                    field_name = sequence_update["field"]
                    field_value = sequence_update["offset"] + sequence_index
                    sequence_index += 1
                    setattr(record, field_name, field_value)
                    updated_fields[field_name] = field_value

                if group_update or sequence_update:
                    await record.save()

                records.append(updated_fields)

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
        raise HTTPException(status_code=400, detail="group_field is required")

    if group_field not in model_class.fields:
        raise HTTPException(
            status_code=400, detail=f"Field '{group_field}' not found on model"
        )

    return {"field": group_field, "value": group_value}


def _prepare_sequence_update(
    model_class: Any, sequence_field: str | None, sequence_offset: int
) -> dict[str, Any] | None:
    """Prepare data for resequencing"""
    if not sequence_field:
        return None

    if sequence_field not in model_class.fields:
        raise HTTPException(
            status_code=400, detail=f"Field '{sequence_field}' not found on model"
        )

    return {
        "field": sequence_field,
        "offset": sequence_offset,
    }


__all__ = [
    "router",
]
