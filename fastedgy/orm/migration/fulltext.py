# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import renderers
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import TSVECTOR


def process_fulltext_revision_directives(context, revision, directives):
    """
    Post-process migration directives to handle the unaccent extension
    when fulltext (TSVECTOR) columns are detected.
    """
    if not directives:
        return

    upgrade_ops = directives[0].upgrade_ops
    if not upgrade_ops:
        return

    if _check_for_tsvector_operations(upgrade_ops.ops):
        directives[0].imports.add(
            "from fastedgy.orm.migration import enable_unaccent_extension"
        )
        directives[0].imports.add("import fastedgy")

        upgrade_ops.ops.insert(0, EnableUnaccentExtensionOperation())


def _check_for_tsvector_operations(ops):
    """Recursively check if any operations use TSVECTOR type."""
    from alembic.operations.ops import AddColumnOp, CreateTableOp, AlterColumnOp

    for op in ops:
        if isinstance(op, AddColumnOp):
            if _is_tsvector_column(op.column):
                return True
        elif isinstance(op, CreateTableOp):
            for column in op.columns:
                if _is_tsvector_column(column):
                    return True
        elif isinstance(op, AlterColumnOp):
            if (
                hasattr(op, "modify_type")
                and op.modify_type
                and _is_tsvector_type(op.modify_type)
            ):
                return True
        elif hasattr(op, "ops"):
            if _check_for_tsvector_operations(op.ops):
                return True
    return False


def _is_tsvector_column(column):
    if not hasattr(column, "type"):
        return False
    return isinstance(column.type, TSVECTOR)


def _is_tsvector_type(type_obj):
    if not type_obj:
        return False
    return isinstance(type_obj, TSVECTOR)


@Operations.register_operation("enable_unaccent_extension")
class EnableUnaccentExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def enable_unaccent_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return DisableUnaccentExtensionOperation()


@Operations.register_operation("disable_unaccent_extension")
class DisableUnaccentExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def disable_unaccent_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return EnableUnaccentExtensionOperation()


@Operations.implementation_for(EnableUnaccentExtensionOperation)
def enable_unaccent_extension_impl(operations, operation) -> None:
    enable_unaccent_extension()


@Operations.implementation_for(DisableUnaccentExtensionOperation)
def disable_unaccent_extension_impl(operations, operation) -> None:
    disable_unaccent_extension()


@renderers.dispatch_for(EnableUnaccentExtensionOperation)
def render_enable_unaccent_extension(_, operation) -> str:
    return "enable_unaccent_extension()"


@renderers.dispatch_for(DisableUnaccentExtensionOperation)
def render_disable_unaccent_extension(_, operation) -> str:
    return "disable_unaccent_extension()"


def enable_unaccent_extension() -> None:
    from alembic import context

    connection = context.get_bind()
    result = connection.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'")
    ).fetchone()

    if not result:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))


def disable_unaccent_extension() -> None:
    from alembic import context

    connection = context.get_bind()
    try:
        connection.execute(text("DROP EXTENSION IF EXISTS unaccent CASCADE"))
    except Exception:
        pass


__all__ = [
    "process_fulltext_revision_directives",
    "EnableUnaccentExtensionOperation",
    "DisableUnaccentExtensionOperation",
    "enable_unaccent_extension",
    "disable_unaccent_extension",
]
