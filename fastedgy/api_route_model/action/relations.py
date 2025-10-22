# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.api_route_model.registry import TypeModel


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


async def process_relational_fields(
    instance: "TypeModel",
    model_cls: type["TypeModel"],
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

        # Handle null or empty array as "clear" action
        if operations is None or (
            isinstance(operations, list) and len(operations) == 0
        ):
            operations = [["clear"]]
        elif operations and isinstance(operations[0], int):
            # Convert simple list[int] to [["set", [ids]]]
            operations = [["set", operations]]

        # Process all relational fields (M2M and O2M) with the same operations
        if is_relation_field(field):
            try:
                await process_relation_operations(
                    instance, field_name, operations, related_model
                )
            except RelationOperationError as e:
                raise HTTPException(status_code=400, detail=str(e))


__all__ = [
    "is_relation_field",
    "get_related_model",
    "process_relational_fields",
]
