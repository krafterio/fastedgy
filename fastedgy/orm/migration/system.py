# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).


def process_system_objects_revision_directives(context, revision, directives):
    """
    Remove operations that target system objects from PostgreSQL extensions.
    """
    _remove_system_objects_operations(context, directives[0].upgrade_ops.ops)


def _get_extension_objects(context):
    """
    Query PostgreSQL to get all tables and views created by extensions.
    Returns a set of object names.
    """
    from sqlalchemy import text

    # Get all objects (tables, views, etc.) that depend on extensions
    result = context.connection.execute(
        text(
            "SELECT DISTINCT c.relname "
            "FROM pg_depend d "
            "JOIN pg_extension e ON d.refobjid = e.oid "
            "JOIN pg_class c ON d.objid = c.oid "
            "WHERE d.deptype = 'e'"
        )
    )

    return {row[0] for row in result}


def _remove_system_objects_operations(context, ops):
    """
    Recursively remove operations that target system objects from PostgreSQL extensions.
    """
    from alembic.operations.ops import DropTableOp, CreateTableOp, ModifyTableOps
    from fastedgy.orm.migration.view_model import (
        DropViewOperation,
        CreateViewOperation,
        ReplaceViewOperation,
    )

    extension_objects = _get_extension_objects(context)
    ops_to_remove = []

    for i, op in enumerate(ops):
        should_remove = False

        if isinstance(op, (DropTableOp, CreateTableOp)):
            if hasattr(op, "table_name") and op.table_name in extension_objects:
                should_remove = True
        elif isinstance(op, ModifyTableOps):
            if hasattr(op, "table_name") and op.table_name in extension_objects:
                should_remove = True
            else:
                # Recursively clean nested operations
                _remove_system_objects_operations(context, op.ops)
                # If ModifyTableOps becomes empty, mark for removal
                if not op.ops:
                    should_remove = True
        elif isinstance(
            op, (DropViewOperation, CreateViewOperation, ReplaceViewOperation)
        ):
            if hasattr(op, "name") and op.name in extension_objects:
                should_remove = True
        elif hasattr(op, "ops"):
            # Recursively clean nested operations
            _remove_system_objects_operations(context, op.ops)

        if should_remove:
            ops_to_remove.append(i)

    # Remove in reverse order to preserve indices
    for i in reversed(ops_to_remove):
        ops.pop(i)


__all__ = [
    "process_system_objects_revision_directives",
]
