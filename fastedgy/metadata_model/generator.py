# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import re

from fastedgy import context
from fastedgy.orm import Model
from fastedgy.orm.fields import BaseFieldType, ForeignKey, ManyToMany, OneToOne
from fastedgy.orm.filter import get_filter_operators, FILTER_FIELD_TYPE_NAME_MAP
from fastedgy.orm.utils import find_primary_key_field
from fastedgy.schemas.dataset import MetadataModel, MetadataField
from fastedgy.schemas import PydanticUndefined


class MetadataFieldError(Exception): ...


def generate_metadata_name(model_cls: type[Model] | Model) -> str:
    class_name = model_cls.__name__
    return re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()


def generate_class_name(metadata_name: str) -> str:
    return re.sub(r"_", " ", metadata_name).title().replace(" ", "")


async def generate_metadata_model(model_cls: Model) -> MetadataModel:
    class_name = model_cls.__name__
    name = generate_metadata_name(model_cls)
    api_name = str(model_cls.meta.tablename)
    label = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)
    label_plural = f"{label}s"
    sortable_field = None

    if hasattr(model_cls.Meta, "label"):
        label = model_cls.Meta.label

    if hasattr(model_cls.Meta, "label_plural"):
        label_plural = model_cls.Meta.label_plural

    if hasattr(model_cls.Meta, "sortable_field"):
        sortable_field = model_cls.Meta.sortable_field
    elif "sequence" in model_cls.meta.fields:
        sortable_field = "sequence"

    fields = await generate_metadata_fields(model_cls)
    has_searchable_fields = False
    for field in fields.values():
        if field.searchable:
            has_searchable_fields = True
            break

    metadata = MetadataModel(
        name=name,
        api_name=api_name,
        label=str(label),
        label_plural=str(label_plural),
        searchable=has_searchable_fields,
        sortable=sortable_field is not None,
        sortable_field=sortable_field,
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


def get_field_choices(field: BaseFieldType) -> dict[str, str] | None:
    """
    Extract choices from a ChoiceField.

    Returns a dict {value: label} or None if not a choice field.
    Order is preserved (Python 3.7+ dicts maintain insertion order).
    """
    if not hasattr(field, "choices") or field.choices is None:
        return None

    # Check if we have custom labels (from fastedgy's ChoiceField)
    if hasattr(field, "_choice_labels") and field._choice_labels:
        return {name: str(label) for name, label in field._choice_labels.items()}

    # Fallback for standard edgy ChoiceField (enum without custom labels)
    return {member.name: str(member.value) for member in field.choices}


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
        choices=get_field_choices(field),
    )


def add_inverse_relations(models: dict[Model, MetadataModel]) -> None:
    """
    Add inverse relations (one2many and many2many) to metadata models.

    Args:
        models: Dictionary mapping Model classes to their MetadataModel
    """
    # Collect all relation modifications to avoid "dictionary changed size during iteration"
    relations_to_add = []

    for model_cls, metadata_model in models.items():
        for field_name, metadata_field in list(metadata_model.fields.items()):
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
                relation_data = _prepare_one_to_many_relation(
                    original_field, model_cls, metadata_model, target_metadata
                )
                if relation_data:
                    relations_to_add.append((target_metadata, relation_data))
            elif isinstance(original_field, ManyToMany):
                relation_data = _prepare_many_to_many_relation(
                    original_field, model_cls, metadata_model, target_metadata
                )
                if relation_data:
                    relations_to_add.append((target_metadata, relation_data))
            elif isinstance(original_field, OneToOne):
                relation_data = _prepare_one_to_one_relation(
                    original_field, model_cls, metadata_model, target_metadata
                )
                if relation_data:
                    relations_to_add.append((target_metadata, relation_data))

    # Apply all collected relations after iteration is complete
    for target_metadata, (field_name, metadata_field) in relations_to_add:
        target_metadata.fields[field_name] = metadata_field


def _find_model_by_metadata_name(
    models: dict[Model, MetadataModel], metadata_name: str
) -> Model | None:
    """Find a Model class by its metadata name."""
    for model_cls, metadata_model in models.items():
        if metadata_model.name == metadata_name:
            return model_cls
    return None


def _prepare_one_to_many_relation(
    foreign_key_field: ForeignKey,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> tuple[str, MetadataField] | None:
    """Prepare one-to-many inverse relation data for target metadata."""
    related_name = getattr(foreign_key_field, "related_name", None)
    if not related_name or related_name.endswith("_set"):
        return None

    if related_name in target_metadata.fields:
        return None

    if hasattr(source_model_cls.Meta, "label_plural"):
        source_label_plural = source_model_cls.Meta.label_plural
    else:
        source_label_plural = f"{source_metadata.label}s"

    metadata_field = MetadataField(
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

    return (related_name, metadata_field)


def _add_one_to_many_relation(
    foreign_key_field: ForeignKey,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> None:
    """Add one-to-many inverse relation to target metadata."""
    relation_data = _prepare_one_to_many_relation(
        foreign_key_field, source_model_cls, source_metadata, target_metadata
    )
    if relation_data:
        field_name, metadata_field = relation_data
        target_metadata.fields[field_name] = metadata_field


def _prepare_many_to_many_relation(
    many_to_many_field: ManyToMany,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> tuple[str, MetadataField] | None:
    """Prepare many-to-many inverse relation data for target metadata."""
    back_populates = getattr(many_to_many_field, "back_populates", None)
    if not back_populates:
        return None

    if back_populates in target_metadata.fields:
        return None

    if hasattr(source_model_cls.Meta, "label_plural"):
        source_label_plural = source_model_cls.Meta.label_plural
    else:
        source_label_plural = f"{source_metadata.label}s"

    metadata_field = MetadataField(
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

    return (back_populates, metadata_field)


def _add_many_to_many_relation(
    many_to_many_field: ManyToMany,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> None:
    """Add many-to-many inverse relation to target metadata."""
    relation_data = _prepare_many_to_many_relation(
        many_to_many_field, source_model_cls, source_metadata, target_metadata
    )
    if relation_data:
        field_name, metadata_field = relation_data
        target_metadata.fields[field_name] = metadata_field


def _prepare_one_to_one_relation(
    one_to_one_field: OneToOne,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> tuple[str, MetadataField] | None:
    """Prepare one-to-one inverse relation data for target metadata."""
    related_name = getattr(one_to_one_field, "related_name", None)
    if not related_name or related_name.endswith("_set"):
        return None

    if related_name in target_metadata.fields:
        return None

    metadata_field = MetadataField(
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

    return (related_name, metadata_field)


def _add_one_to_one_relation(
    one_to_one_field: OneToOne,
    source_model_cls: Model,
    source_metadata: MetadataModel,
    target_metadata: MetadataModel,
) -> None:
    """Add one-to-one inverse relation to target metadata."""
    relation_data = _prepare_one_to_one_relation(
        one_to_one_field, source_model_cls, source_metadata, target_metadata
    )
    if relation_data:
        field_name, metadata_field = relation_data
        target_metadata.fields[field_name] = metadata_field


__all__ = [
    "MetadataFieldError",
    "generate_metadata_name",
    "generate_class_name",
    "generate_metadata_model",
    "generate_metadata_fields",
    "add_extra_fields",
    "get_filter_operators_for_extra_field",
    "get_field_choices",
    "generate_metadata_field_type",
    "generate_metadata_field",
    "add_inverse_relations",
]
