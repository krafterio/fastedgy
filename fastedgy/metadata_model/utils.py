# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm import Model
from fastedgy.schemas.dataset import MetadataField
from fastedgy.metadata_model.generator import generate_metadata_field


def get_metadata_field_from_path(model_cls: type[Model], field_path: str) -> MetadataField | None:
    if not field_path:
        return None

    parts = field_path.split('.')
    current_model = model_cls
    current_field = None

    for i, part in enumerate(parts):
        if not current_model or not hasattr(current_model, 'meta') or not hasattr(current_model.meta, 'fields'):
            return None

        field = current_model.meta.fields.get(part)

        if not field:
            return None

        current_field = field

        if i < len(parts) - 1 and hasattr(field, 'target'):
            current_model = field.target
        else:
            current_model = None

    if current_field and current_model:
        return generate_metadata_field(current_model, current_field) # type: ignore

    if current_field:

        parent_model = model_cls

        for part in parts[:-1]:
            field = parent_model.meta.fields.get(part)

            if field and hasattr(field, 'target'):
                parent_model = field.target
            else:
                return None

        return generate_metadata_field(parent_model, current_field) # type: ignore

    return None


def get_field_label_from_path(model_cls: type[Model], field_path: str) -> str:

    if not field_path or '.' not in field_path:
        metadata_field = get_metadata_field_from_path(model_cls, field_path)

        if metadata_field:
            return metadata_field.label

        return field_path

    parts = field_path.split('.')
    labels = []
    current_model = model_cls

    for i, part in enumerate(parts):
        if not current_model or not hasattr(current_model, 'meta') or not hasattr(current_model.meta, 'fields'):
            labels.append(part)

            continue

        field = current_model.meta.fields.get(part)

        if not field:
            labels.append(part)
            continue

        if hasattr(field, 'label') and field.label:
            labels.append(field.label)
        else:
            name_parts = field.name.split('_')
            label = name_parts[0].capitalize()

            if len(name_parts) > 1:
                label = ' '.join([name_parts[0].capitalize()] + [word.lower() for word in name_parts[1:]])

            labels.append(label)

        if i < len(parts) - 1 and hasattr(field, 'target'):
            current_model = field.target
        else:
            current_model = None

    return " / ".join(labels)


__all__ = [
    "get_metadata_field_from_path",
    "get_field_label_from_path",
]
