# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import re
import sqlparse

from collections import defaultdict

from alembic.autogenerate.api import AutogenContext
from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import comparators, renderers
from alembic.operations.ops import UpgradeOps
from sqlalchemy import text

from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.orm.view import TableView


@comparators.dispatch_for("schema")
def compare_view(
    autogen_context: AutogenContext, upgrade_ops: UpgradeOps, schemas
) -> None:
    # Define all views from the database
    registry = get_service(Registry)
    db_views = defaultdict()

    # Get views created by extensions (PostGIS, etc.)
    extension_views = set()
    try:
        ext_rows = autogen_context.connection.execute(  # type: ignore
            text(
                "SELECT DISTINCT c.relname "
                "FROM pg_depend d "
                "JOIN pg_extension e ON d.refobjid = e.oid "
                "JOIN pg_class c ON d.objid = c.oid "
                "WHERE c.relkind = 'v' AND d.deptype = 'e'"
            )
        )
        extension_views = {row[0] for row in ext_rows}
    except Exception:
        pass

    for sch in schemas:
        rows = autogen_context.connection.execute(  # type: ignore
            text(
                "SELECT table_schema, table_name, view_definition "
                "FROM information_schema.views "
                "WHERE table_schema=:nspname"
            ),
            {
                "nspname": autogen_context.dialect.default_schema_name
                if sch is None
                else sch,  # type: ignore
            },
        )

        for row in rows:
            if row[1] not in extension_views:
                db_views[(row[0], row[1])] = normalize_sql(row[2])

    # Define all views from the models
    model_views = defaultdict()

    for model in registry.models.values():
        if isinstance(model.table, TableView):
            for sch in schemas:
                schema = (
                    autogen_context.dialect.default_schema_name if sch is None else sch
                )  # type: ignore
                definition = normalize_sql(
                    str(
                        model.table.selectable.compile(
                            dialect=autogen_context.dialect,
                            compile_kwargs={"literal_binds": True},
                        )
                    )
                )
                model_views[(schema, model.meta.tablename)] = definition

    # Collect view operations
    drop_ops = []
    create_ops = []
    replace_ops = []

    # Drop old views
    for key, db_def in db_views.items():
        if key not in model_views:
            schema, name = key
            drop_ops.append(DropViewOperation(name, db_def))

    # Create new views
    for key, model_def in model_views.items():
        if key not in db_views:
            schema, name = key
            create_ops.append(CreateViewOperation(name, model_def))

    # Replace views
    for key in model_views.keys() & db_views.keys():
        model_def = model_views[key]
        model_def_for_db = normalize_sql(model_def, True)
        db_def = db_views[key]

        if model_def_for_db != db_def:
            schema, name = key
            if _check_db_view_difference(
                autogen_context.connection, name, model_def, db_def, schema
            ):
                replace_ops.append(ReplaceViewOperation(name, model_def, db_def))

    # Add operations (they will be reordered later by fastedgy_process_revision_directives)
    for op in drop_ops:
        upgrade_ops.ops.append(op)

    for op in create_ops + replace_ops:
        upgrade_ops.ops.append(op)


@Operations.register_operation("create_view")
class CreateViewOperation(MigrateOperation):
    def __init__(self, name: str, definition: str) -> None:
        self.name: str = name
        self.definition: str = definition

    @classmethod
    def create_view(cls, operations, name: str, definition: str) -> None:
        return operations.invoke(cls(name, definition))

    def reverse(self) -> MigrateOperation:
        return DropViewOperation(self.name, self.definition)


@Operations.register_operation("drop_view")
class DropViewOperation(MigrateOperation):
    def __init__(self, name: str, reverse_definition: str) -> None:
        self.name: str = name
        self.reverse_definition: str = reverse_definition

    @classmethod
    def drop_view(cls, operations, name: str, reverse_definition: str) -> None:
        return operations.invoke(cls(name, reverse_definition))

    def reverse(self) -> MigrateOperation:
        return CreateViewOperation(self.name, self.reverse_definition)


@Operations.register_operation("replace_view")
class ReplaceViewOperation(MigrateOperation):
    def __init__(
        self, name: str, definition: str, reverse_definition: str | None
    ) -> None:
        self.name: str = name
        self.definition: str = definition
        self.reverse_definition: str | None = reverse_definition

    @classmethod
    def replace_view(
        cls, operations, name: str, definition: str, reverse_definition: str
    ) -> None:
        operations.invoke(cls(name, definition, reverse_definition))

    def reverse(self) -> MigrateOperation:
        return ReplaceViewOperation(self.name, self.reverse_definition, self.definition)  # type: ignore


@Operations.implementation_for(CreateViewOperation)
def create_view(operations, operation: CreateViewOperation) -> None:
    operations.execute(f"CREATE VIEW {operation.name} AS {operation.definition}")


@Operations.implementation_for(DropViewOperation)
def drop_view(operations, operation: DropViewOperation) -> None:
    operations.execute(f"DROP VIEW IF EXISTS {operation.name} CASCADE")


@Operations.implementation_for(ReplaceViewOperation)
def replace_view(operations, operation: ReplaceViewOperation) -> None:
    operations.execute(f"DROP VIEW IF EXISTS {operation.name} CASCADE")
    operations.execute(
        f"CREATE OR REPLACE VIEW {operation.name} AS {operation.definition}"
    )


@renderers.dispatch_for(CreateViewOperation)
def render_create_view(_, operation: CreateViewOperation) -> str:
    escaped_definition = operation.definition.replace("'", "\\'")
    return f"op.create_view('{operation.name}', '''{escaped_definition}''')"


@renderers.dispatch_for(DropViewOperation)
def render_drop_view(_, operation: DropViewOperation) -> str:
    escaped_definition = operation.reverse_definition.replace("'", "\\'")
    return f"op.drop_view('{operation.name}', '''{escaped_definition}''')"


@renderers.dispatch_for(ReplaceViewOperation)
def render_replace_view(_, operation: ReplaceViewOperation) -> str:
    escaped_definition = operation.definition.replace("'", "\\'")
    escaped_reverse = (
        operation.reverse_definition.replace("'", "\\'")
        if operation.reverse_definition
        else ""
    )
    return f"op.replace_view('{operation.name}', '''{escaped_definition}''', '''{escaped_reverse}''')"


def normalize_sql(sql: str, clean_null_cast: bool = False) -> str:
    formatted = sqlparse.format(
        sql,
        keyword_case="lower",
        identifier_case="lower",
        strip_comments=True,
        reindent=False,
        use_space_around_operators=True,
    )

    formatted = re.sub(
        r"(::)\s*[a-zA-Z0-9_.\s]+?(\s+varying)?(?=\s+as\s+|\s*,|\s*\)|\s*$)",
        "",
        formatted,
    )
    formatted = re.sub(r"varchar(\([0-9]+\))?", "", formatted, flags=re.IGNORECASE)
    formatted = re.sub(
        r"character varying(\([0-9]+\))?", "", formatted, flags=re.IGNORECASE
    )
    formatted = re.sub(r"\s+", " ", formatted)
    formatted = re.sub(r"\(\s*", "(", formatted)
    formatted = re.sub(r"\s*\)", ")", formatted)
    formatted = re.sub(
        r'([a-zA-Z0-9_."()]+)\s+as\s+("[a-zA-Z0-9_]+"|[a-zA-Z0-9_]+)',
        _remove_redundant_aliases,
        formatted,
        flags=re.IGNORECASE,
    )

    if clean_null_cast:
        formatted = re.sub(
            r"cast\s*\(\s*null\s+as\s+[^)]+\)", "null", sql, flags=re.IGNORECASE
        )

    formatted = formatted.strip()
    formatted = formatted.strip(";")

    return formatted


def process_view_model_revision_directives(context, revision, directives) -> None:
    if directives[0].upgrade_ops:
        _reorder_view_model_operations(directives[0].upgrade_ops)


def _reorder_view_model_operations(upgrade_ops: UpgradeOps) -> None:
    """
    Reorder operations to ensure view operations are in the correct order:
    - Drop views at the beginning (before table modifications)
    - Create/Replace views at the end (after table modifications)

    This prevents errors when views depend on newly created/modified columns.
    """
    drop_views = []
    create_replace_views = []
    other_ops = []

    for op in upgrade_ops.ops:
        if isinstance(op, DropViewOperation):
            drop_views.append(op)
        elif isinstance(op, (CreateViewOperation, ReplaceViewOperation)):
            create_replace_views.append(op)
        else:
            other_ops.append(op)

    # Reorder: drops first, then table ops, then creates/replaces
    upgrade_ops.ops[:] = drop_views + other_ops + create_replace_views


def _remove_redundant_aliases(match):
    expr = match.group(1).strip()
    alias = match.group(2).strip().strip('"')
    expr_last = expr.split(".")[-1].strip('"')

    if expr_last == alias:
        return expr

    return match.group(0)


def _check_db_view_difference(
    connection, view_name: str, model_def: str, db_def: str, schema: str = "public"
) -> bool:
    """
    Check if a view definition is different from the database view.

    This function creates a temporary view with the model's SQL definition,
    reads PostgreSQL's normalized version, and compares it with the existing
    view's SQL. This eliminates false positives from SQL formatting differences.

    Returns True if the views are truly different, False otherwise.
    """
    temp_view_name = f"_alembic_temp_check_{view_name}"

    try:
        connection.execute(text(f"DROP VIEW IF EXISTS {temp_view_name} CASCADE"))
        connection.commit()

        connection.execute(text(f"CREATE VIEW {temp_view_name} AS {model_def}"))
        connection.commit()

        result = connection.execute(
            text(
                "SELECT view_definition FROM information_schema.views "
                "WHERE table_schema = :schema AND table_name = :name"
            ),
            {"schema": schema, "name": temp_view_name},
        )
        row = result.fetchone()

        if not row:
            return True

        temp_normalized = normalize_sql(row[0])

        connection.execute(text(f"DROP VIEW IF EXISTS {temp_view_name} CASCADE"))
        connection.commit()

        return temp_normalized != db_def

    except Exception:
        try:
            connection.execute(text(f"DROP VIEW IF EXISTS {temp_view_name} CASCADE"))
            connection.commit()
        except:
            pass

        return True


__all__ = [
    "compare_view",
    "CreateViewOperation",
    "DropViewOperation",
    "ReplaceViewOperation",
    "normalize_sql",
    "process_view_model_revision_directives",
]
