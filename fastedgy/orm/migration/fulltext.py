# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from sqlalchemy.dialects.postgresql import TSVECTOR

from .unaccent import EnableUnaccentExtensionOperation
from .pg_trgm import EnablePgTrgmExtensionOperation


def process_fulltext_revision_directives(context, revision, directives):
    """
    Post-process migration directives to enable required extensions
    (unaccent + pg_trgm) when TSVECTOR columns are detected.
    """
    if not directives:
        return

    upgrade_ops = directives[0].upgrade_ops
    if not upgrade_ops:
        return

    if _check_for_tsvector_operations(upgrade_ops.ops):
        directives[0].imports.add(
            "from fastedgy.orm.migration import enable_unaccent_extension, enable_pg_trgm_extension"
        )
        directives[0].imports.add("import fastedgy")

        upgrade_ops.ops.insert(0, EnablePgTrgmExtensionOperation())
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


__all__ = [
    "process_fulltext_revision_directives",
]
