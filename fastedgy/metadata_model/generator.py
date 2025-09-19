# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import re

from fastedgy import context
from fastedgy.orm import Model
from fastedgy.orm.fields import BaseFieldType, ForeignKey, ManyToMany, OneToOne
from fastedgy.orm.filter import get_filter_operators, FILTER_FIELD_TYPE_NAME_MAP
from fastedgy.orm.utils import find_primary_key_field
from fastedgy.schemas.dataset import MetadataModel, MetadataField
from pydantic_core import PydanticUndefined


class MetadataFieldError(Exception): ...


def generate_metadata_name(model_cls: type[Model] | Model) -> str:
    class_name = model_cls.__name__
    return re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()


def generate_class_name(metadata_name: str) -> str:
    return re.sub(r"_", " ", metadata_name).title().replace(" ", "")


async def generate_metadata_model(model_cls: Model) -> MetadataModel:
    class_name = model_cls.__name__
    name = generate_metadata_name(model_cls)
    label = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)
    label_plural = f"{label}s"

    if hasattr(model_cls.Meta, "label"):
        label = model_cls.Meta.label

    if hasattr(model_cls.Meta, "label_plural"):
        label_plural = model_cls.Meta.label_plural

    fields = await generate_metadata_fields(model_cls)
    has_searchable_fields = False
    for field in fields.values():
        if field.searchable:
            has_searchable_fields = True
            break

    metadata = MetadataModel(
        name=name,
        label=str(label),
        label_plural=str(label_plural),
        searchable=has_searchable_fields,
        fields=fields,
    )

    return metadata


async def generate_metadata_fields(model_cls: Model) -> dict[str, MetadataField]:
    fields = {}
    for field_name, field_info in model_cls.meta.fields.items():
        if not field_info.exclude or (
            hasattr(field_info, "is_m2m") and field_info.is_m2m
        ):
            fields[field_name] = generate_metadata_field(model_cls, field_info)

    await add_extra_fields(model_cls, fields)

    return fields


async def add_extra_fields(model_cls: Model, fields: dict[str, MetadataField]) -> None:
    from fastedgy.models.workspace_extra_field import EXTRA_FIELDS_MAP

    model_name = generate_metadata_name(model_cls)

    for extra_field in context.get_workspace_extra_fields(model_name):
        field_class = EXTRA_FIELDS_MAP.get(extra_field.field_type)

        if not field_class:
            continue

        fields[f"extra_{extra_field.name}"] = MetadataField(
            name=f"extra_{extra_field.name}",
            label=str(extra_field.label),
            type=generate_metadata_field_type(field_class),
            readonly=False,
            required=extra_field.required,
            searchable=True,
            extra=True,
            filter_operators=get_filter_operators_for_extra_field(
                extra_field.field_type
            ),
            target=None,
        )


def get_filter_operators_for_extra_field(field_type) -> list[str]:
    from fastedgy.models.workspace_extra_field import EXTRA_FIELDS_MAP
    from fastedgy.orm.filter import FILTER_OPERATORS_FIELD_MAP

    field_class = EXTRA_FIELDS_MAP.get(field_type)
    if not field_class:
        return []

    return FILTER_OPERATORS_FIELD_MAP.get(field_class, [])


def generate_metadata_field_type(field: BaseFieldType) -> str:
    if name := FILTER_FIELD_TYPE_NAME_MAP.get(field.__class__.__name__):
        return name

    field_type = type(field).__name__

    if field_type == "FieldFactoryMeta":
        field_type = field.__name__

    field_type = field_type[:-5] if field_type.endswith("Field") else field_type

    return re.sub(r"(?<!^)(?=[A-Z])", "_", field_type).lower()


def generate_metadata_field(model_cls: Model, field: BaseFieldType) -> MetadataField:
    name_parts = field.name.split("_")
    label = name_parts[0].capitalize()
    if len(name_parts) > 1:
        label = " ".join(
            [name_parts[0].capitalize()] + [word.lower() for word in name_parts[1:]]
        )

    field_type = generate_metadata_field_type(field)
    readonly = field.read_only
    has_default = field.default is not None and field.default != PydanticUndefined
    required = not field.null and not field.read_only

    if find_primary_key_field(model_cls) == field.name:
        readonly = True

    target_model = field.target if field and hasattr(field, "target") else None
    label = field.label if field and hasattr(field, "label") else label
    filter_operators = get_filter_operators(field)
    searchable = (
        field.searchable
        if field and hasattr(field, "searchable")
        else len(filter_operators) > 0
    )

    if searchable and not filter_operators:
        raise MetadataFieldError(
            f"Metadata field {field.name} must have a filter operator if searchable is enabled"
        )

    return MetadataField(
        name=field.name,
        label=str(label),
        type=field_type,
        readonly=readonly,
        required=required and not readonly and not has_default,
        searchable=searchable,
        extra=False,
        filter_operators=filter_operators,
        target=generate_metadata_name(target_model) if target_model else None,
    )


def add_inverse_relations(models: dict[Model, MetadataModel]) -> None:
    """
    Add inverse relations (one2many and many2many) to metadata models.

    Args:
        models: Dictionary mapping Model classes to their MetadataModel
    """
    for model_cls, metadata_model in models.items():
        for field_name, metadata_field in metadata_model.fields.items():
            if not metadata_field.target:
                continue

            original_field = model_cls.meta.fields.get(field_name)
            if not original_field:
                continue

            target_model_name = metadata_field.target
            target_model_cls = _find_model_by_metadata_name(models, target_model_name)
            if not target_model_cls:
                continue

            target_metadata = models[target_model_cls]

            if isinstance(original_field, ForeignKey):
                _add_one_to_many_relation(
                    original_field, model_cls, metadata_model, target_metadata
                )
            elif isinstance(original_field, ManyToMany):
                _add_many_to_many_relation(
                    original_field, model_cls, metadata_model, target_metadata
                )
            elif isinstance(original_field, OneToOne):
                _add_one_to_one_relation(
                    original_field, model_cls, metadata_model, target_metadata
                )


def _find_model_by_metadata_name(
    models: dict[Model, MetadataModel], metadata_name: str
) -> Model | None:
    """Find a Model class by its metadata name."""
    for model_cls, metadata_model in models.items():
        if metadata_model.name == metadata_name:
            return model_cls
    return None


def _add_one_to_many_relation(
    foreign_key_field: ForeignKey,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> None:
    """Add one-to-many inverse relation to target metadata."""
    related_name = getattr(foreign_key_field, "related_name", None)
    if not related_name or related_name.endswith("_set"):
        return

    if related_name in target_metadata.fields:
        return

    if hasattr(source_model_cls.Meta, "label_plural"):
        source_label_plural = source_model_cls.Meta.label_plural
    else:
        source_label_plural = f"{source_metadata.label}s"

    target_metadata.fields[related_name] = MetadataField(
        name=related_name,
        label=str(source_label_plural),
        type=FILTER_FIELD_TYPE_NAME_MAP["OneToMany"],
        readonly=True,
        required=False,
        searchable=True,
        extra=False,
        filter_operators=get_filter_operators("OneToMany"),
        target=source_metadata.name,
    )


def _add_many_to_many_relation(
    many_to_many_field: ManyToMany,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> None:
    """Add many-to-many inverse relation to target metadata."""
    back_populates = getattr(many_to_many_field, "back_populates", None)
    if not back_populates:
        return

    if back_populates in target_metadata.fields:
        return

    if hasattr(source_model_cls.Meta, "label_plural"):
        source_label_plural = source_model_cls.Meta.label_plural
    else:
        source_label_plural = f"{source_metadata.label}s"

    target_metadata.fields[back_populates] = MetadataField(
        name=back_populates,
        label=str(source_label_plural),
        type=FILTER_FIELD_TYPE_NAME_MAP["ManyToMany"],
        readonly=True,
        required=False,
        searchable=True,
        extra=False,
        filter_operators=get_filter_operators(ManyToMany),
        target=source_metadata.name,
    )


def _add_one_to_one_relation(
    one_to_one_field: OneToOne,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> None:
    """Add one-to-one inverse relation to target metadata."""
    related_name = getattr(one_to_one_field, "related_name", None)
    if not related_name or related_name.endswith("_set"):
        return

    if related_name in target_metadata.fields:
        return

    target_metadata.fields[related_name] = MetadataField(
        name=related_name,
        label=str(source_metadata.label),
        type=FILTER_FIELD_TYPE_NAME_MAP["OneToOne"],
        readonly=True,
        required=False,
        searchable=True,
        extra=False,
        filter_operators=get_filter_operators(OneToOne),
        target=source_metadata.name,
    )


__all__ = [
    "MetadataFieldError",
    "generate_metadata_name",
    "generate_class_name",
    "generate_metadata_model",
    "generate_metadata_fields",
    "add_extra_fields",
    "get_filter_operators_for_extra_field",
    "generate_metadata_field_type",
    "generate_metadata_field",
    "add_inverse_relations",
]
