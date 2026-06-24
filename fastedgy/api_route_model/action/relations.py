# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.api_route_model.registry import TypeModel
from fastedgy.models.base import BaseModel


def is_relation_field(field) -> bool:
    """
    Check if a field is a relational field (M2M or O2M).

    Args:
        field: The field to check

    Returns:
        True if the field is a Many-to-Many or One-to-Many field
    """
    from edgy.core.db.relationships.related_field import RelatedField

    # M2M fields have is_m2m attribute (direct M2M declaration)
    # RelatedField covers both M2M and O2M reverse relations (via related_name)
    return getattr(field, "is_m2m", False) is True or isinstance(field, RelatedField)


def is_exposed_relation_field(field) -> bool:
    """
    Check if a relation field is part of the public API surface.

    Direct many-to-many declarations are always intentional. Reverse relations
    (RelatedField) are exposed only when their related_name was set explicitly:
    Edgy auto-generates a ``<model>s_set`` reverse accessor for every foreign key,
    and a ``+`` placeholder when the reverse relation is disabled, both of which
    are ORM internals rather than API fields. This mirrors the metadata generator,
    which also skips reverse relations whose name ends with ``_set``.

    Args:
        field: The field to check

    Returns:
        True if the relation should appear in the input/output schemas
    """
    if not is_relation_field(field):
        return False

    if getattr(field, "is_m2m", False) is True:
        return True

    related_name = getattr(field, "related_name", None) or getattr(field, "name", None)

    if not related_name or related_name == "+":
        return False

    return not related_name.endswith("_set")


def get_related_model(field) -> type:
    """
    Extract the related model class from a relational field.

    Args:
        field: A ManyToMany, ForeignKey, or RelatedField (O2M)

    Returns:
        The related model class

    Raises:
        AttributeError: If the field doesn't have appropriate attributes
    """
    from edgy.core.db.relationships.related_field import RelatedField

    # For RelatedField (O2M via related_name), use related_from
    if isinstance(field, RelatedField):
        return field.related_from

    # For M2M and FK fields, the 'target' property resolves the related model
    return field.target


def is_foreign_key_field(field) -> bool:
    """
    Check if a field is a (forward) foreign key.

    Args:
        field: The field to check

    Returns:
        True if the field is a ForeignKey (excluding M2M/O2M reverse relations)
    """
    from edgy.core.db.fields.foreign_keys import ForeignKey

    return isinstance(field, ForeignKey)


def _plain_foreign_key_value(value: Any) -> Any:
    """Normalize a validated foreign key input to plain Python data.

    PATCH reads values straight off the Pydantic model, so unwrap the shared
    ``ForeignKeyOperation`` RootModel and ``ForeignKeyObject`` model into the
    tuple/dict the processor expects (CREATE already dumps them via model_dump).
    """
    if value is None or isinstance(value, (int, dict, list, tuple)):
        return value

    root = getattr(value, "root", None)
    if root is not None:
        return list(root) if isinstance(root, tuple) else root

    if hasattr(value, "model_dump"):
        return value.model_dump()

    return value


async def process_foreign_key_fields(
    model_cls: "TypeModel",
    foreign_key_data: dict[str, Any],
) -> tuple[dict[str, int | None], list["BaseModel"]]:
    """
    Resolve foreign key inputs to the ids to store on the instance.

    Each value may be an id, an object ({"id": ...} with optional updates), null
    (unlink) or a single advanced-mode operation. Related records are created or
    updated before the id is returned; records targeted by a ``delete`` operation
    are returned for deletion once the owning instance has been saved.

    Args:
        model_cls: The model class
        foreign_key_data: Dictionary of field_name -> foreign key input

    Returns:
        A tuple of (field_name -> resolved id or None, records to delete after save)

    Raises:
        HTTPException: If a foreign key operation fails
    """
    from fastedgy.orm.relations.processor import process_foreign_key_operation
    from fastedgy.orm.relations.utils import RelationOperationError
    from fastapi import HTTPException

    resolved: dict[str, int | None] = {}
    deferred_deletes: list["BaseModel"] = []

    for field_name, value in foreign_key_data.items():
        field = model_cls.model_fields[field_name]

        try:
            record_id, to_delete = await process_foreign_key_operation(
                get_related_model(field),
                _plain_foreign_key_value(value),
                nullable=getattr(field, "null", False),
                field_name=field_name,
            )
        except RelationOperationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        resolved[field_name] = record_id

        if to_delete is not None:
            deferred_deletes.append(to_delete)

    return resolved, deferred_deletes


async def process_relational_fields(
    instance: "BaseModel",
    model_cls: "TypeModel",
    relational_data: dict[str, Any],
) -> None:
    """
    Process relational fields (M2M and O2M) operations after instance save.

    Args:
        instance: The saved model instance
        model_cls: The model class
        relational_data: Dictionary of field_name -> operations

    Raises:
        HTTPException: If a relation operation fails
    """
    from fastedgy.orm.relations.processor import process_relation_operations
    from fastedgy.orm.relations.utils import RelationOperationError
    from fastapi import HTTPException

    for field_name, operations in relational_data.items():
        field = model_cls.model_fields[field_name]
        related_model = get_related_model(field)

        # Advanced-mode operations validate as RelationOperation (RootModel) items;
        # unwrap them back to plain tuples for the operation processor.
        if isinstance(operations, list):
            operations = [getattr(op, "root", op) for op in operations]

        # Handle null or empty array as "clear" action
        if operations is None or (isinstance(operations, list) and len(operations) == 0):
            operations = [["clear"]]
        elif operations and isinstance(operations[0], int):
            # Convert simple list[int] to [["set", [ids]]]
            operations = [["set", operations]]

        # Process all relational fields (M2M and O2M) with the same operations
        if is_relation_field(field):
            try:
                await process_relation_operations(instance, field_name, operations, related_model)
            except RelationOperationError as e:
                raise HTTPException(status_code=400, detail=str(e))


__all__ = [
    "is_relation_field",
    "is_exposed_relation_field",
    "is_foreign_key_field",
    "get_related_model",
    "process_relational_fields",
    "process_foreign_key_fields",
]
