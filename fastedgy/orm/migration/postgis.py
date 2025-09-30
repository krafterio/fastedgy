# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import renderers
from sqlalchemy import text


def process_postgis_revision_directives(context, revision, directives):
    """
    Post-process migration directives to handle PostGIS geometry columns and postgis extension.
    """
    if not directives:
        return

    upgrade_ops = directives[0].upgrade_ops
    if not upgrade_ops:
        return

    postgis_operations_found = _check_for_postgis_operations(upgrade_ops.ops)

    if postgis_operations_found:
        directives[0].imports.add(
            "from fastedgy.orm.migration import enable_postgis_extension"
        )
        directives[0].imports.add("import fastedgy")

        upgrade_ops.ops.insert(0, EnablePostGISExtensionOperation())


def _check_for_postgis_operations(ops):
    """Recursively check if any operations use PostGIS geometry types"""
    from alembic.operations.ops import AddColumnOp, CreateTableOp, AlterColumnOp

    for op in ops:
        if isinstance(op, AddColumnOp):
            if _is_postgis_column(op.column):
                return True
        elif isinstance(op, CreateTableOp):
            for column in op.columns:
                if _is_postgis_column(column):
                    return True
        elif isinstance(op, AlterColumnOp):
            if (
                hasattr(op, "modify_type")
                and op.modify_type
                and _is_postgis_type(op.modify_type)
            ):
                return True
            if (
                hasattr(op, "existing_type")
                and op.existing_type
                and _is_postgis_type(op.existing_type)
            ):
                return True
        elif hasattr(op, "ops"):
            if _check_for_postgis_operations(op.ops):
                return True
    return False


def _is_postgis_column(column):
    """Check if a column uses PostGIS geometry type"""
    if not hasattr(column, "type"):
        return False

    from fastedgy.orm.fields import Point

    return isinstance(column.type, Point)


def _is_postgis_type(type_obj):
    """Check if a type is a PostGIS Point type"""
    if not type_obj:
        return False

    from fastedgy.orm.fields import Point

    return isinstance(type_obj, Point)


@Operations.register_operation("enable_postgis_extension")
class EnablePostGISExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def enable_postgis_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return DisablePostGISExtensionOperation()


@Operations.register_operation("disable_postgis_extension")
class DisablePostGISExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def disable_postgis_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return EnablePostGISExtensionOperation()


@Operations.implementation_for(EnablePostGISExtensionOperation)
def enable_postgis_extension_impl(
    operations, operation: EnablePostGISExtensionOperation
) -> None:
    enable_postgis_extension()


@Operations.implementation_for(DisablePostGISExtensionOperation)
def disable_postgis_extension_impl(
    operations, operation: DisablePostGISExtensionOperation
) -> None:
    disable_postgis_extension()


@renderers.dispatch_for(EnablePostGISExtensionOperation)
def render_enable_postgis_extension(_, operation: EnablePostGISExtensionOperation) -> str:
    return "enable_postgis_extension()"


@renderers.dispatch_for(DisablePostGISExtensionOperation)
def render_disable_postgis_extension(
    _, operation: DisablePostGISExtensionOperation
) -> str:
    return "disable_postgis_extension()"


def enable_postgis_extension() -> None:
    """
    Enable the PostGIS extension for PostgreSQL.
    This function is idempotent - it won't fail if the extension is already enabled.
    """
    from alembic import context

    connection = context.get_bind()

    result = connection.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
    ).fetchone()

    if not result:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))


def disable_postgis_extension() -> None:
    """
    Disable the PostGIS extension for PostgreSQL.
    Warning: This will fail if there are still tables using PostGIS types.
    """
    from alembic import context

    connection = context.get_bind()

    try:
        connection.execute(text("DROP EXTENSION IF EXISTS postgis CASCADE"))
    except Exception:
        pass


__all__ = [
    "process_postgis_revision_directives",
    "EnablePostGISExtensionOperation",
    "DisablePostGISExtensionOperation",
    "enable_postgis_extension",
    "disable_postgis_extension",
]
