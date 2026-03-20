# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from alembic.operations import Operations, MigrateOperation
from alembic.autogenerate import renderers
from sqlalchemy import text


@Operations.register_operation("enable_pg_trgm_extension")
class EnablePgTrgmExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def enable_pg_trgm_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return DisablePgTrgmExtensionOperation()


@Operations.register_operation("disable_pg_trgm_extension")
class DisablePgTrgmExtensionOperation(MigrateOperation):
    def __init__(self) -> None:
        pass

    @classmethod
    def disable_pg_trgm_extension(cls, operations) -> None:
        return operations.invoke(cls())

    def reverse(self) -> MigrateOperation:
        return EnablePgTrgmExtensionOperation()


@Operations.implementation_for(EnablePgTrgmExtensionOperation)
def enable_pg_trgm_extension_impl(operations, operation) -> None:
    enable_pg_trgm_extension()


@Operations.implementation_for(DisablePgTrgmExtensionOperation)
def disable_pg_trgm_extension_impl(operations, operation) -> None:
    disable_pg_trgm_extension()


@renderers.dispatch_for(EnablePgTrgmExtensionOperation)
def render_enable_pg_trgm_extension(_, operation) -> str:
    return "enable_pg_trgm_extension()"


@renderers.dispatch_for(DisablePgTrgmExtensionOperation)
def render_disable_pg_trgm_extension(_, operation) -> str:
    return "disable_pg_trgm_extension()"


def enable_pg_trgm_extension() -> None:
    """Enable the pg_trgm PostgreSQL extension."""
    from alembic import context

    connection = context.get_bind()
    result = connection.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    ).fetchone()
    if not result:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


def disable_pg_trgm_extension() -> None:
    """Disable the pg_trgm PostgreSQL extension."""
    from alembic import context

    connection = context.get_bind()
    try:
        connection.execute(text("DROP EXTENSION IF EXISTS pg_trgm CASCADE"))
    except Exception:
        pass


__all__ = [
    "EnablePgTrgmExtensionOperation",
    "DisablePgTrgmExtensionOperation",
    "enable_pg_trgm_extension",
    "disable_pg_trgm_extension",
]
