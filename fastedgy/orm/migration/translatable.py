# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

import sqlalchemy as sa
from alembic.autogenerate import renderers
from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate.render import _repr_type
from alembic.operations import MigrateOperation, Operations
from alembic.operations.ops import AddColumnOp, AlterColumnOp, CreateTableOp
from sqlalchemy.dialects.postgresql import JSONB


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def translatable_from_text(column_name: str, fallback_locale: str) -> str:
    """The SQL turning a text column into a translatable one: its text becomes the fallback locale's."""
    column = _identifier(column_name)

    return f"CASE WHEN {column} IS NULL THEN NULL ELSE jsonb_build_object({_literal(fallback_locale)}, {column}) END"


def text_from_translatable(column_name: str, fallback_locale: str) -> str:
    """The SQL turning a translatable column back into a text one: the fallback locale's text is kept."""
    return f"{_identifier(column_name)} ->> {_literal(fallback_locale)}"


@Operations.register_operation("convert_to_translatable")
class ConvertToTranslatableOperation(MigrateOperation):
    def __init__(
        self,
        table_name: str,
        column_name: str,
        fallback_locale: str,
        existing_type: Any = None,
        schema: str | None = None,
    ) -> None:
        self.table_name = table_name
        self.column_name = column_name
        self.fallback_locale = fallback_locale
        self.existing_type = existing_type
        self.schema = schema

    @classmethod
    def convert_to_translatable(
        cls,
        operations: Operations,
        table_name: str,
        column_name: str,
        fallback_locale: str,
        existing_type: Any = None,
        schema: str | None = None,
    ) -> None:
        return operations.invoke(cls(table_name, column_name, fallback_locale, existing_type, schema))

    def reverse(self) -> MigrateOperation:
        return ConvertFromTranslatableOperation(
            self.table_name,
            self.column_name,
            self.fallback_locale,
            self.existing_type if self.existing_type is not None else sa.Text(),
            self.schema,
        )


@Operations.register_operation("convert_from_translatable")
class ConvertFromTranslatableOperation(MigrateOperation):
    def __init__(
        self,
        table_name: str,
        column_name: str,
        fallback_locale: str,
        type_: Any,
        schema: str | None = None,
    ) -> None:
        self.table_name = table_name
        self.column_name = column_name
        self.fallback_locale = fallback_locale
        self.type_ = type_
        self.schema = schema

    @classmethod
    def convert_from_translatable(
        cls,
        operations: Operations,
        table_name: str,
        column_name: str,
        fallback_locale: str,
        type_: Any,
        schema: str | None = None,
    ) -> None:
        return operations.invoke(cls(table_name, column_name, fallback_locale, type_, schema))

    def reverse(self) -> MigrateOperation:
        return ConvertToTranslatableOperation(
            self.table_name,
            self.column_name,
            self.fallback_locale,
            self.type_,
            self.schema,
        )


@Operations.implementation_for(ConvertToTranslatableOperation)
def convert_to_translatable(operations: Operations, operation: ConvertToTranslatableOperation) -> None:
    operations.alter_column(
        operation.table_name,
        operation.column_name,
        type_=JSONB(),
        existing_type=operation.existing_type,
        postgresql_using=translatable_from_text(operation.column_name, operation.fallback_locale),
        schema=operation.schema,
    )


@Operations.implementation_for(ConvertFromTranslatableOperation)
def convert_from_translatable(operations: Operations, operation: ConvertFromTranslatableOperation) -> None:
    operations.alter_column(
        operation.table_name,
        operation.column_name,
        type_=operation.type_,
        existing_type=JSONB(),
        postgresql_using=text_from_translatable(operation.column_name, operation.fallback_locale),
        schema=operation.schema,
    )


def _render_arguments(
    autogen_context: AutogenContext,
    operation: ConvertToTranslatableOperation | ConvertFromTranslatableOperation,
    type_name: str,
    type_: Any,
) -> str:
    arguments = [
        repr(operation.table_name),
        repr(operation.column_name),
        f"fallback_locale={operation.fallback_locale!r}",
    ]

    if type_ is not None:
        arguments.append(f"{type_name}={_repr_type(type_, autogen_context)}")

    if operation.schema:
        arguments.append(f"schema={operation.schema!r}")

    return ", ".join(arguments)


@renderers.dispatch_for(ConvertToTranslatableOperation)
def render_convert_to_translatable(autogen_context: AutogenContext, operation: ConvertToTranslatableOperation) -> str:
    return f"op.convert_to_translatable({_render_arguments(autogen_context, operation, 'existing_type', operation.existing_type)})"


@renderers.dispatch_for(ConvertFromTranslatableOperation)
def render_convert_from_translatable(
    autogen_context: AutogenContext, operation: ConvertFromTranslatableOperation
) -> str:
    return f"op.convert_from_translatable({_render_arguments(autogen_context, operation, 'type_', operation.type_)})"


def _is_translatable(type_: Any) -> bool:
    from fastedgy.orm.fields import Translatable

    return isinstance(type_, Translatable)


def _conversion(op: AlterColumnOp) -> MigrateOperation | None:
    """The operation converting the stored values of a column turning translatable, or turning back to text.

    The document a translatable column holds is no text PostgreSQL casts on its
    own: the type change needs to say what becomes of each value.
    """
    from fastedgy.context import get_fallback_locale

    new, old = op.modify_type, op.existing_type

    if _is_translatable(new) and isinstance(old, sa.String):
        return ConvertToTranslatableOperation(op.table_name, op.column_name, get_fallback_locale(), old, op.schema)

    if isinstance(new, sa.String) and (_is_translatable(old) or isinstance(old, sa.JSON)):
        return ConvertFromTranslatableOperation(op.table_name, op.column_name, get_fallback_locale(), new, op.schema)

    return None


def _alters_more_than_its_type(op: AlterColumnOp) -> bool:
    return (
        op.modify_nullable is not None
        or op.modify_server_default is not False
        or op.modify_comment is not False
        or op.modify_name is not None
    )


def _process_ops(ops: list[Any]) -> bool:
    """Swap each type change in or out of a translatable column for its conversion. True if any translatable type
    is left for the script to render."""
    renders_type = False

    for index in range(len(ops) - 1, -1, -1):
        op = ops[index]

        if isinstance(op, CreateTableOp):
            renders_type = renders_type or any(_is_translatable(getattr(c, "type", None)) for c in op.columns)
        elif isinstance(op, AddColumnOp):
            renders_type = renders_type or _is_translatable(op.column.type)
        elif isinstance(op, AlterColumnOp):
            conversion = _conversion(op)

            if conversion is None:
                renders_type = renders_type or _is_translatable(op.modify_type) or _is_translatable(op.existing_type)
                continue

            op.existing_type, op.modify_type = op.modify_type, None
            renders_type = renders_type or _is_translatable(op.existing_type)
            ops[index : index + 1] = [conversion, op] if _alters_more_than_its_type(op) else [conversion]
        elif hasattr(op, "ops"):
            renders_type = _process_ops(op.ops) or renders_type

    return renders_type


def process_translatable_revision_directives(context: Any, revision: Any, directives: list[Any]) -> None:
    """
    Post-process migration directives to convert the values of the columns turning translatable or back to text.
    """
    if not directives:
        return

    script = directives[0]
    renders_type = False

    for ops in (script.upgrade_ops, script.downgrade_ops):
        if ops is not None:
            renders_type = _process_ops(ops.ops) or renders_type

    if renders_type:
        script.imports.add("import fastedgy")


__all__ = [
    "ConvertFromTranslatableOperation",
    "ConvertToTranslatableOperation",
    "process_translatable_revision_directives",
    "text_from_translatable",
    "translatable_from_text",
]
