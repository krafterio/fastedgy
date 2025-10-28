# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Processor for executing relation operations."""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fastedgy.models.base import BaseModel

from fastedgy.orm.relations.utils import (
    extract_id,
    extract_id_and_values,
    RelationOperationError,
)


async def process_relation_operations(
    instance: "BaseModel",
    field_name: str,
    operations: list[list[Any]] | list[tuple[str, Any]],
    related_model: type["BaseModel"],
) -> None:
    """
    Process relational operations (M2M or O2M) for a given field.

    Operations are executed sequentially in the order provided.
    Each operation is validated and will raise an error if it fails.

    Works for both Many-to-Many and One-to-Many relationships as they
    share the same relation manager interface.

    Args:
        instance: The model instance
        field_name: Name of the relational field (M2M or O2M)
        operations: List of [action, value] lists (from API) or tuples
        related_model: The related model class

    Raises:
        RelationOperationError: If an operation fails (ID not found, invalid data, etc.)

    Examples:
        >>> await process_relation_operations(
        ...     product,
        ...     "tags",
        ...     [["link", 1], ["create", {"name": "New"}]],
        ...     Tag
        ... )
        >>> await process_relation_operations(
        ...     company,
        ...     "contacts",
        ...     [["create", {"name": "John"}], ["unlink", 5]],
        ...     Contact
        ... )
    """
    relation_manager = getattr(instance, field_name)

    for op in operations:
        # Convert list to tuple if needed and validate structure
        if not isinstance(op, (list, tuple)) or len(op) < 1:
            raise RelationOperationError(
                f"Invalid operation format: {op}. Expected [action, ...] format."
            )

        op_tuple = tuple(op) if isinstance(op, list) else op
        action = op_tuple[0]

        if not isinstance(action, str):
            raise RelationOperationError(
                f"Invalid action type: {type(action).__name__}. Expected string."
            )

        try:
            if action == "create":
                _, values = op_tuple
                if not isinstance(values, dict):
                    raise RelationOperationError(
                        f"create requires dict of values, got: {type(values).__name__}"
                    )

                # For O2M (reverse) relationships, automatically add parent FK if not provided
                # Find the FK field in related_model that points back to instance
                parent_model = instance.__class__
                fk_field_name = None

                for (
                    candidate_name,
                    candidate_field,
                ) in related_model.model_fields.items():
                    # Check if this field is a FK pointing to the parent model
                    if hasattr(candidate_field, "target"):
                        try:
                            if candidate_field.target == parent_model:
                                fk_field_name = candidate_name
                                break
                        except Exception:
                            pass

                # Add parent FK to values if not already present
                if fk_field_name and fk_field_name not in values:
                    values[fk_field_name] = instance.id

                new_record = await related_model.query.create(**values)
                await relation_manager.add(new_record)

            elif action == "update":
                _, value = op_tuple
                record_id, update_values = extract_id_and_values(value)

                record = await related_model.query.get(id=record_id)
                if not record:
                    raise RelationOperationError(
                        f"Record with id={record_id} not found in {related_model.__name__}"
                    )

                for key, val in update_values.items():
                    setattr(record, key, val)
                await record.save()

                # Ensure it's linked
                current_ids = {r.id for r in await relation_manager.all()}
                if record.id not in current_ids:
                    await relation_manager.add(record)

            elif action == "link":
                _, value = op_tuple
                record_id = extract_id(value)

                record = await related_model.query.get(id=record_id)
                if not record:
                    raise RelationOperationError(
                        f"Record with id={record_id} not found in {related_model.__name__}"
                    )

                await relation_manager.add(record)

            elif action == "unlink":
                _, value = op_tuple
                record_id = extract_id(value)

                record = await related_model.query.get(id=record_id)
                if not record:
                    raise RelationOperationError(
                        f"Record with id={record_id} not found in {related_model.__name__}"
                    )

                await relation_manager.remove(record)

            elif action == "delete":
                _, value = op_tuple
                record_id = extract_id(value)

                record = await related_model.query.get(id=record_id)
                if not record:
                    raise RelationOperationError(
                        f"Record with id={record_id} not found in {related_model.__name__}"
                    )

                await relation_manager.remove(record)
                await record.delete()

            elif action == "clear":
                related_instances = await relation_manager.all()

                # For O2M (reverse) relationships with NOT NULL FK, we need to delete records
                # instead of just removing the link (which tries to set FK to NULL)
                parent_model = instance.__class__
                fk_field_name = None
                is_fk_nullable = True

                # Find the FK field pointing to parent
                for (
                    candidate_name,
                    candidate_field,
                ) in related_model.model_fields.items():
                    if hasattr(candidate_field, "target"):
                        try:
                            if candidate_field.target == parent_model:
                                fk_field_name = candidate_name
                                is_fk_nullable = getattr(candidate_field, "null", True)
                                break
                        except Exception:
                            pass

                # If FK is NOT NULL, we must delete records; otherwise just remove the link
                if fk_field_name and not is_fk_nullable:
                    # For NOT NULL FK, delete records directly (don't try to remove/unlink)
                    for related_instance in related_instances:
                        await related_instance.delete()
                else:
                    # For nullable FK, just remove the link
                    for related_instance in related_instances:
                        await relation_manager.remove(related_instance)

            elif action == "set":
                _, ids = op_tuple
                if not isinstance(ids, list):
                    raise RelationOperationError(
                        f"set requires list of IDs, got: {type(ids).__name__}"
                    )

                # Validate all IDs exist before modifying
                records_to_link = []
                for record_id in ids:
                    if not isinstance(record_id, int) or record_id <= 0:
                        raise RelationOperationError(
                            f"Invalid ID in set operation: {record_id}"
                        )

                    record = await related_model.query.get(id=record_id)
                    if not record:
                        raise RelationOperationError(
                            f"Record with id={record_id} not found in {related_model.__name__}"
                        )
                    records_to_link.append(record)

                # Get current IDs
                current = await relation_manager.all()
                current_ids = {r.id for r in current}
                target_ids = set(ids)

                # Check if FK is NOT NULL for O2M handling
                parent_model = instance.__class__
                is_fk_nullable = True

                for (
                    candidate_name,
                    candidate_field,
                ) in related_model.model_fields.items():
                    if hasattr(candidate_field, "target"):
                        try:
                            if candidate_field.target == parent_model:
                                is_fk_nullable = getattr(candidate_field, "null", True)
                                break
                        except Exception:
                            pass

                # Unlink removed IDs
                to_unlink = current_ids - target_ids
                for record in current:
                    if record.id in to_unlink:
                        # For NOT NULL FK, delete records directly; otherwise just remove the link
                        if not is_fk_nullable:
                            await record.delete()
                        else:
                            await relation_manager.remove(record)

                # Link new IDs
                to_link = target_ids - current_ids
                for record in records_to_link:
                    if record.id in to_link:
                        await relation_manager.add(record)

            else:
                raise RelationOperationError(f"Unknown operation: {action}")

        except RelationOperationError:
            raise
        except Exception as e:
            raise RelationOperationError(
                f"Error executing {action} operation on {field_name}: {str(e)}"
            ) from e
