# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import inspect
import sqlalchemy as sa

from enum import Enum

from alembic.autogenerate.api import AutogenContext
from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import comparators, renderers
from alembic.operations.ops import UpgradeOps
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from fastedgy.dependencies import get_service
from fastedgy.orm import Registry


def process_enum_revision_directives(context, revision, directives):
    """
    Post-process migration directives to fix enum column definitions.
    """
    if not directives:
        return

    upgrade_ops = directives[0].upgrade_ops
    if not upgrade_ops:
        return

    # Find all enums that will be created in this migration
    enums_being_created = set()
    for op in upgrade_ops.ops:
        if hasattr(op, '__class__') and op.__class__.__name__ == 'CreateEnumOperation':
            if hasattr(op, 'enum_name'):
                enums_being_created.add(op.enum_name)

    if not enums_being_created:
        return

    # Process all operations to fix enum column types
    _replace_enum_column_types(upgrade_ops.ops, enums_being_created)

    # Add fastedgy import to the migration
    if enums_being_created:
        directives[0].imports.add("import fastedgy")


def _replace_enum_column_types(ops, enums_being_created):
    """Recursively replace enum column types in all operations"""
    from alembic.operations.ops import AddColumnOp, CreateTableOp

    for op in ops:
        if isinstance(op, AddColumnOp):
            # Replace single column in AddColumnOp
            _replace_column_enum_by_reference_enum(op.column, enums_being_created)
        elif isinstance(op, CreateTableOp):
            # Replace all columns in CreateTableOp
            for column in op.columns:
                _replace_column_enum_by_reference_enum(column, enums_being_created)
        elif hasattr(op, 'ops'):
            # Recursively process nested operations (like batch operations)
            _replace_enum_column_types(op.ops, enums_being_created)


def _replace_column_enum_by_reference_enum(column, enums_being_created):
    """Replace a single column's enum type if it references an enum being created"""
    if not hasattr(column, 'type'):
        return

    if isinstance(column.type, sa.Enum):
        enum_name = column.type.name
        if enum_name:
            column.type = ReferenceEnum(name=enum_name)
    elif isinstance(column.type, postgresql.ENUM) and not isinstance(column.type, ReferenceEnum):
        # Replace regular postgresql.ENUM with our custom type when it has a name
        if hasattr(column.type, 'name') and column.type.name:
            # Use our custom type that always renders with create_type=False
            column.type = ReferenceEnum(name=column.type.name)


@comparators.dispatch_for("schema")
def compare_enums(autogen_context: AutogenContext, upgrade_ops: UpgradeOps, schemas) -> None:
    # Get all enums from the database
    registry = get_service(Registry)
    db_enums = {}

    for sch in schemas:
        rows = autogen_context.connection.execute( # type: ignore
            text(
                "SELECT t.typname, e.enumlabel "
                "FROM pg_type t "
                "JOIN pg_enum e ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON t.typnamespace = n.oid "
                "WHERE n.nspname=:nspname "
                "ORDER BY t.typname, e.enumsortorder"
            ),
            {
                "nspname": autogen_context.dialect.default_schema_name if sch is None else sch, # type: ignore
            }
        )

        for row in rows:
            enum_name, enum_value = row
            if enum_name not in db_enums:
                db_enums[enum_name] = []
            db_enums[enum_name].append(enum_value)

    # Get current default values for enum columns from database
    db_enum_defaults = {}
    for sch in schemas:
        default_rows = autogen_context.connection.execute( # type: ignore
            text(
                "SELECT c.table_name, c.column_name, c.column_default, t.typname "
                "FROM information_schema.columns c "
                "JOIN pg_type t ON c.udt_name = t.typname "
                "JOIN pg_namespace n ON t.typnamespace = n.oid "
                "WHERE n.nspname=:nspname "
                "AND t.typtype = 'e' "
                "AND c.column_default IS NOT NULL"
            ),
            {
                "nspname": autogen_context.dialect.default_schema_name if sch is None else sch, # type: ignore
            }
        )

        for row in default_rows:
            table_name, column_name, column_default, enum_name = row
            # Clean up the default value (remove quotes and type cast)
            clean_default = column_default.split("'")[1] if "'" in column_default else column_default
            if enum_name not in db_enum_defaults:
                db_enum_defaults[enum_name] = {}
            if table_name not in db_enum_defaults[enum_name]:
                db_enum_defaults[enum_name][table_name] = {}
            db_enum_defaults[enum_name][table_name][column_name] = clean_default

    # Get all enums from models and their default values
    model_enums = {}
    model_enum_defaults = {}

    for model in registry.models.values():
        for field_name, field in model.meta.fields.items():
            # Check for ChoiceField with enum
            choices = getattr(field, 'choices', None)
            if choices and inspect.isclass(choices) and issubclass(choices, Enum):
                enum_class = choices
                enum_name = enum_class.__name__.lower()
                table_name = model.meta.tablename

                # Convert to the actual postgres enum name format
                if enum_name not in model_enums:
                    model_enums[enum_name] = [e.name for e in enum_class]

                # Check if field has a default value
                field_default = getattr(field, 'default', None)
                if field_default is not None and _is_valid_default_value(field_default):
                    if enum_name not in model_enum_defaults:
                        model_enum_defaults[enum_name] = {}
                    if table_name not in model_enum_defaults[enum_name]:
                        model_enum_defaults[enum_name][table_name] = {}

                    # Convert enum instance to string if needed
                    if isinstance(field_default, Enum):
                        field_default = field_default.name
                    model_enum_defaults[enum_name][table_name][field_name] = field_default

    # Compare and create operations
    for enum_name, model_values in model_enums.items():
        if enum_name in db_enums:
            db_values = db_enums[enum_name]
            db_defaults = db_enum_defaults.get(enum_name, {})
            model_defaults = model_enum_defaults.get(enum_name, {})

            # Check if enum values or default values have changed
            enum_values_changed = set(model_values) != set(db_values)
            default_values_changed = _compare_default_values(db_defaults, model_defaults)

            if enum_values_changed or default_values_changed:
                # Validate that new default values exist in new enum
                _validate_default_values(model_defaults, model_values, enum_name)

                # Generate automatic mapping for removed enum values
                automatic_mapping = _generate_automatic_enum_mapping(db_values, model_values, enum_name, autogen_context)

                upgrade_ops.ops.append(ReplaceEnumOperation(
                    enum_name,
                    model_values,
                    db_values,
                    automatic_mapping,  # Auto-generated value_mapping
                    model_defaults,
                    db_defaults
                ))
        else:
            # New enum - no need for defaults since no columns use it yet
            # Insert at the beginning so enums are created before tables
            upgrade_ops.ops.insert(0, CreateEnumOperation(enum_name, model_values))

    # Check for dropped enums
    for enum_name, db_values in db_enums.items():
        if enum_name not in model_enums:
            upgrade_ops.ops.append(DropEnumOperation(enum_name, db_values))


def _is_valid_default_value(value) -> bool:
    """
    Check if a value is a valid enum default value.
    Filters out Pydantic/Edgy special values like PydanticUndefined.
    """
    if value is None:
        return False

    # Convert to string to check for special markers
    value_str = str(value)

    # Filter out Pydantic/Edgy special values
    if value_str in ['PydanticUndefined', 'Undefined', '<PydanticUndefined>']:
        return False

    # Filter out callable defaults (functions)
    if callable(value):
        return False

    return True


def _compare_default_values(db_defaults: dict, model_defaults: dict) -> bool:
    """Compare default values between database and models"""
    # Convert both to flat dictionaries for easier comparison
    db_flat = {}
    for table_name, columns in db_defaults.items():
        for column_name, default_value in columns.items():
            db_flat[f"{table_name}.{column_name}"] = default_value

    model_flat = {}
    for table_name, columns in model_defaults.items():
        for column_name, default_value in columns.items():
            model_flat[f"{table_name}.{column_name}"] = default_value

    return db_flat != model_flat


def _validate_default_values(model_defaults: dict, enum_values: list[str], enum_name: str) -> None:
    """Validate that all default values exist in the new enum values"""
    for table_name, columns in model_defaults.items():
        for column_name, default_value in columns.items():
            if default_value not in enum_values:
                raise ValueError(
                    f"Default value '{default_value}' for column '{table_name}.{column_name}' "
                    f"does not exist in enum '{enum_name}' values: {enum_values}"
                )


def _generate_automatic_enum_mapping(old_values: list[str], new_values: list[str], enum_name: str, autogen_context: AutogenContext) -> dict[str, str | None] | None:
    """
    Generate automatic value mapping for enum migration when values are removed/added.
    Returns mapping dict or None if no mapping needed.
    """
    removed_values = set(old_values) - set(new_values)

    if not removed_values:
        return None

    # Check if columns using this enum are nullable
    is_nullable = False
    try:
        result = autogen_context.connection.execute( # type: ignore
            text(
                "SELECT c.is_nullable FROM information_schema.columns c "
                "JOIN pg_type t ON c.udt_name = t.typname "
                "JOIN pg_namespace n ON t.typnamespace = n.oid "
                "WHERE t.typname = :enum_name AND n.nspname = :schema_name "
                "LIMIT 1"
            ),
            {
                "enum_name": enum_name,
                "schema_name": autogen_context.dialect.default_schema_name or "public" # type: ignore
            }
        ).fetchone()

        if result:
            is_nullable = result[0] == "YES"
    except Exception:
        # Fallback if query fails
        is_nullable = False

    mapping = {}
    for removed_value in removed_values:
        if is_nullable:
            # Map to null if column is nullable
            mapping[removed_value] = None
        elif new_values:
            # Map to first new value if column is not nullable
            mapping[removed_value] = new_values[0]
        else:
            # This shouldn't happen but fallback to None
            mapping[removed_value] = None

    return mapping if mapping else None


def create_enum_value_mapping(*renames: tuple[str, str]) -> dict[str, str]:
    """
    Helper to create value mapping for enum migrations.

    Usage:
        # For renaming enum values
        mapping = create_enum_value_mapping(
            ('draft', 'pending'),
            ('active', 'published')
        )
        op.replace_enum('status', ['pending', 'published'], ['draft', 'active'], mapping)
    """
    return dict(renames)


class ReferenceEnum(postgresql.ENUM):
    """
    Custom PostgreSQL ENUM type that always renders with create_type=False.
    """

    def __init__(self, *enums, **kwargs):
        kwargs['create_type'] = False
        super().__init__(*enums, **kwargs)


@Operations.register_operation("replace_enum")
class ReplaceEnumOperation(MigrateOperation):
    def __init__(
        self,
        enum_name: str,
        new_values: list[str],
        old_values: list[str],
        value_mapping: dict[str, str | None] | None = None,
        new_defaults: dict[str, dict[str, str]] | None = None,
        old_defaults: dict[str, dict[str, str]] | None = None
    ) -> None:
        self.enum_name: str = enum_name
        self.new_values: list[str] = new_values
        self.old_values: list[str] = old_values
        self.value_mapping: dict[str, str | None] | None = value_mapping
        self.new_defaults: dict[str, dict[str, str]] | None = new_defaults or {}
        self.old_defaults: dict[str, dict[str, str]] | None = old_defaults or {}

    @classmethod
    def replace_enum(
        cls,
        operations,
        enum_name: str,
        new_values: list[str],
        old_values: list[str],
        value_mapping: dict[str, str | None] | None = None,
        new_defaults: dict[str, dict[str, str]] | None = None,
        old_defaults: dict[str, dict[str, str]] | None = None
    ) -> None:
        return operations.invoke(cls(enum_name, new_values, old_values, value_mapping, new_defaults, old_defaults))

    def reverse(self) -> MigrateOperation:
        reverse_mapping = None
        if self.value_mapping:
            reverse_mapping = {}
            for k, v in self.value_mapping.items():
                if v is not None:  # Only reverse non-null mappings
                    reverse_mapping[v] = k
                # Null mappings can't be reversed directly
        return ReplaceEnumOperation(
            self.enum_name,
            self.old_values,
            self.new_values,
            reverse_mapping,
            self.old_defaults,
            self.new_defaults
        )


@Operations.register_operation("create_enum")
class CreateEnumOperation(MigrateOperation):
    def __init__(self, enum_name: str, values: list[str]) -> None:
        self.enum_name: str = enum_name
        self.values: list[str] = values

    @classmethod
    def create_enum(cls, operations, enum_name: str, values: list[str]) -> None:
        return operations.invoke(cls(enum_name, values))

    def reverse(self) -> MigrateOperation:
        return DropEnumOperation(self.enum_name, self.values)


@Operations.register_operation("drop_enum")
class DropEnumOperation(MigrateOperation):
    def __init__(self, enum_name: str, reverse_values: list[str]) -> None:
        self.enum_name: str = enum_name
        self.reverse_values: list[str] = reverse_values

    @classmethod
    def drop_enum(cls, operations, enum_name: str, reverse_values: list[str]) -> None:
        return operations.invoke(cls(enum_name, reverse_values))

    def reverse(self) -> MigrateOperation:
        return CreateEnumOperation(self.enum_name, self.reverse_values)


@Operations.register_operation("rename_enum")
class RenameEnumOperation(MigrateOperation):
    def __init__(self, old_name: str, new_name: str) -> None:
        self.old_name: str = old_name
        self.new_name: str = new_name

    @classmethod
    def rename_enum(cls, operations, old_name: str, new_name: str) -> None:
        return operations.invoke(cls(old_name, new_name))

    def reverse(self) -> MigrateOperation:
        return RenameEnumOperation(self.new_name, self.old_name)


@Operations.implementation_for(ReplaceEnumOperation)
def replace_enum(operations, operation: ReplaceEnumOperation) -> None:
    enum_name = operation.enum_name
    old_enum_name = f"{enum_name}_old"
    new_values = operation.new_values

    # Rename old enum
    operations.execute(f"ALTER TYPE {enum_name} RENAME TO {old_enum_name}")

    # Create new enum with new values
    new_enum = sa.Enum(*new_values, name=enum_name)
    new_enum.create(operations.get_bind())

    # Find all tables using this enum and update them
    result = operations.get_bind().execute(sa.text(
        "SELECT table_name, column_name, is_nullable FROM information_schema.columns WHERE udt_name = :old_enum_name"
    ), {"old_enum_name": old_enum_name})

    for row in result:
        table_name, column_name, is_nullable = row
        default_value = f"'{new_values[0]}'" if new_values else "null"

        # First, drop any existing default to avoid cast errors during type change
        operations.execute(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP DEFAULT")

        # Build CASE statement for value conversion
        if operation.value_mapping:
            # Use custom mapping provided by user
            case_conditions = []
            for old_val, new_val in operation.value_mapping.items():
                if new_val is None:
                    case_conditions.append(f"WHEN {column_name}::text = '{old_val}' THEN null")
                else:
                    case_conditions.append(f"WHEN {column_name}::text = '{old_val}' THEN '{new_val}'::{enum_name}")

            # Add case-insensitive fallback for unmapped values
            case_insensitive_conditions = []
            for new_val in new_values:
                case_insensitive_conditions.append(f"WHEN LOWER({column_name}::text) = LOWER('{new_val}') THEN '{new_val}'::{enum_name}")

            # Final fallback
            if is_nullable == "YES":
                final_fallback = "null"
            else:
                final_fallback = f"{default_value}::{enum_name}"

            case_statement = f"""CASE
                {' '.join(case_conditions)}
                {' '.join(case_insensitive_conditions)}
                ELSE {final_fallback}
            END"""
        else:
            # Use automatic mapping (existing values that match new enum values)
            # First try exact match, then case-insensitive match
            case_insensitive_conditions = []
            for new_val in new_values:
                case_insensitive_conditions.append(f"WHEN LOWER({column_name}::text) = LOWER('{new_val}') THEN '{new_val}'::{enum_name}")

            if is_nullable == "YES":
                case_statement = f"""CASE
                    WHEN {column_name}::text = ANY(ARRAY{new_values}) THEN {column_name}::text::{enum_name}
                    {' '.join(case_insensitive_conditions)}
                    ELSE null
                END"""
            else:
                case_statement = f"""CASE
                    WHEN {column_name}::text = ANY(ARRAY{new_values}) THEN {column_name}::text::{enum_name}
                    {' '.join(case_insensitive_conditions)}
                    ELSE {default_value}::{enum_name}
                END"""

        operations.execute(f"""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name}
            TYPE {enum_name}
            USING {case_statement}
        """)

        # Update default values if they have changed
        new_default = None
        if operation.new_defaults and table_name in operation.new_defaults:
            new_default = operation.new_defaults[table_name].get(column_name)

        old_default = None
        if operation.old_defaults and table_name in operation.old_defaults:
            old_default = operation.old_defaults[table_name].get(column_name)

        # Only update if default value has actually changed
        if new_default != old_default:
            if new_default is not None:
                # Set new default value
                operations.execute(f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name}
                    SET DEFAULT '{new_default}'::{enum_name}
                """)
            else:
                # Remove default value
                operations.execute(f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name}
                    DROP DEFAULT
                """)

    # Drop old enum
    sa.Enum(name=old_enum_name).drop(operations.get_bind(), checkfirst=True)


@Operations.implementation_for(CreateEnumOperation)
def create_enum(operations, operation: CreateEnumOperation) -> None:
    result = operations.get_bind().execute(sa.text("SELECT 1 FROM pg_type WHERE typname = :enum_name"), {"enum_name": operation.enum_name}).fetchone()

    if result:
        return

    enum = sa.Enum(*operation.values, name=operation.enum_name)
    enum.create(operations.get_bind())


@Operations.implementation_for(DropEnumOperation)
def drop_enum(operations, operation: DropEnumOperation) -> None:
    sa.Enum(name=operation.enum_name).drop(operations.get_bind(), checkfirst=True)


@Operations.implementation_for(RenameEnumOperation)
def rename_enum(operations, operation: RenameEnumOperation) -> None:
    operations.execute(f"ALTER TYPE {operation.old_name} RENAME TO {operation.new_name}")


@renderers.dispatch_for(ReplaceEnumOperation)
def render_replace_enum(_, operation: ReplaceEnumOperation) -> str:
    new_values_repr = repr(operation.new_values)
    old_values_repr = repr(operation.old_values)

    args = [f"'{operation.enum_name}'", new_values_repr, old_values_repr]

    if operation.value_mapping:
        args.append(repr(operation.value_mapping))
    else:
        args.append("None")

    if operation.new_defaults:
        args.append(repr(operation.new_defaults))
    else:
        args.append("None")

    if operation.old_defaults:
        args.append(repr(operation.old_defaults))
    else:
        args.append("None")

    return f"op.replace_enum({', '.join(args)})"


@renderers.dispatch_for(CreateEnumOperation)
def render_create_enum(_, operation: CreateEnumOperation) -> str:
    values_repr = repr(operation.values)
    return f"op.create_enum('{operation.enum_name}', {values_repr})"


@renderers.dispatch_for(DropEnumOperation)
def render_drop_enum(_, operation: DropEnumOperation) -> str:
    reverse_values_repr = repr(operation.reverse_values)
    return f"op.drop_enum('{operation.enum_name}', {reverse_values_repr})"


@renderers.dispatch_for(RenameEnumOperation)
def render_rename_enum(_, operation: RenameEnumOperation) -> str:
    return f"op.rename_enum('{operation.old_name}', '{operation.new_name}')"


@renderers.dispatch_for(ReferenceEnum)
def render_reference_enum(_, type_):
    """Custom renderer for PostgreSQL ENUM that always includes create_type=False"""
    args = []

    if hasattr(type_, 'enums') and type_.enums:
        enum_values = ', '.join(repr(val) for val in type_.enums)
        args.append(enum_values)

    if hasattr(type_, 'name') and type_.name:
        args.append(f"name={repr(type_.name)}")

    args.append("create_type=False")

    args_str = ', '.join(args)

    return f"postgresql.ENUM({args_str})"


__all__ = [
    "process_enum_revision_directives",
    "compare_enums",
    "ReplaceEnumOperation",
    "CreateEnumOperation",
    "DropEnumOperation",
    "RenameEnumOperation",
    "ReferenceEnum",
    "create_enum_value_mapping",
]
