# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import renderers
from sqlalchemy import text


def process_vector_revision_directives(context, revision, directives):
    """
    Post-process migration directives to handle vector columns and pgvector extension.
    """
    if not directives:
        return

    upgrade_ops = directives[0].upgrade_ops
    if not upgrade_ops:
        return

    # Check if any operations use vector types
    vector_operations_found = _check_for_vector_operations(upgrade_ops.ops)

    if vector_operations_found:
        # Add imports needed for vector operations
        directives[0].imports.add("from fastedgy.orm.migration import enable_vector_extension")
        directives[0].imports.add("import fastedgy")

        # Insert enable_vector_extension call at the beginning of upgrade operations
        upgrade_ops.ops.insert(0, EnableVectorExtensionOperation())


def _check_for_vector_operations(ops):
    """Recursively check if any operations use vector types"""
    from alembic.operations.ops import AddColumnOp, CreateTableOp, AlterColumnOp

    for op in ops:
        if isinstance(op, AddColumnOp):
            if _is_vector_column(op.column):
                return True
        elif isinstance(op, CreateTableOp):
            for column in op.columns:
                if _is_vector_column(column):
                    return True
        elif isinstance(op, AlterColumnOp):
            if hasattr(op, 'modify_type') and op.modify_type and _is_vector_type(op.modify_type):
                return True
            if hasattr(op, 'existing_type') and op.existing_type and _is_vector_type(op.existing_type):
                return True
        elif hasattr(op, 'ops'):
            if _check_for_vector_operations(op.ops):
                return True
    return False


def _is_vector_column(column):
    """Check if a column uses vector type"""
    if not hasattr(column, 'type'):
        return False

    from fastedgy.orm.fields import Vector
    return isinstance(column.type, Vector)


def _is_vector_type(type_obj):
    """Check if a type is a Vector type"""
    if not type_obj:
        return False

    from fastedgy.orm.fields import Vector
    return isinstance(type_obj, Vector)


@Operations.register_operation("enable_vector_extension")
class EnableVectorExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def enable_vector_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return DisableVectorExtensionOperation()


@Operations.register_operation("disable_vector_extension")
class DisableVectorExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def disable_vector_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return EnableVectorExtensionOperation()


@Operations.implementation_for(EnableVectorExtensionOperation)
def enable_vector_extension_impl(operations, operation: EnableVectorExtensionOperation) -> None:
    enable_vector_extension()


@Operations.implementation_for(DisableVectorExtensionOperation)
def disable_vector_extension_impl(operations, operation: DisableVectorExtensionOperation) -> None:
    disable_vector_extension()


@renderers.dispatch_for(EnableVectorExtensionOperation)
def render_enable_vector_extension(_, operation: EnableVectorExtensionOperation) -> str:
    return "enable_vector_extension()"


@renderers.dispatch_for(DisableVectorExtensionOperation)
def render_disable_vector_extension(_, operation: DisableVectorExtensionOperation) -> str:
    return "disable_vector_extension()"


def enable_vector_extension() -> None:
    """
    Enable the vector extension for PostgreSQL (pgvector).
    This function is idempotent - it won't fail if the extension is already enabled.
    """
    from alembic import context

    connection = context.get_bind()

    result = connection.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ).fetchone()

    if not result:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def disable_vector_extension() -> None:
    """
    Disable the vector extension for PostgreSQL (pgvector).
    Warning: This will fail if there are still tables using the vector type.
    """
    from alembic import context

    connection = context.get_bind()

    try:
        connection.execute(text("DROP EXTENSION IF EXISTS vector CASCADE"))
    except Exception:
        pass


__all__ = [
    "process_vector_revision_directives",
    "EnableVectorExtensionOperation",
    "DisableVectorExtensionOperation",
    "enable_vector_extension",
    "disable_vector_extension",
]
