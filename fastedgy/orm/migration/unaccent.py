# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import renderers
from sqlalchemy import text


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
    """Enable the unaccent PostgreSQL extension."""
    from alembic import context

    connection = context.get_bind()
    result = connection.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'")
    ).fetchone()
    if not result:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))


def disable_unaccent_extension() -> None:
    """Disable the unaccent PostgreSQL extension."""
    from alembic import context

    connection = context.get_bind()
    try:
        connection.execute(text("DROP EXTENSION IF EXISTS unaccent CASCADE"))
    except Exception:
        pass


__all__ = [
    "EnableUnaccentExtensionOperation",
    "DisableUnaccentExtensionOperation",
    "enable_unaccent_extension",
    "disable_unaccent_extension",
]
