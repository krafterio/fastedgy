# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import sys
import threading

from fastedgy import cli
from fastedgy.cli import console, CliContext
from fastedgy.cli.db import db


# Monkey-patch to ignore _DeleteDummyThreadOnDel exception at process termination with Python 3.13
_old = threading._DeleteDummyThreadOnDel.__del__ # type: ignore
def _safe_del(self):
    if sys and sys.is_finalizing():
        return
    try:
        _old(self)
    except Exception:
        pass
threading._DeleteDummyThreadOnDel.__del__ = _safe_del # type: ignore


@db.command()
@cli.pass_cli_context
async def createdb(ctx: CliContext):
    """Create the database"""
    from fastedgy.orm import Database
    from sqlalchemy.engine.url import make_url

    db_url = make_url(ctx.settings.database_url).set(database="postgres")
    admin_database_url = (
        f"{db_url.drivername}://"
        f"{db_url.username}:{db_url.password}@"
        f"{db_url.host or ''}"
        f"{':' + str(db_url.port) if db_url.port else ''}/"
        f"{db_url.database}"
    )
    dbname = ctx.settings.db_name

    db_admin = Database(admin_database_url)
    await db_admin.connect()
    result = await db_admin.execute("SELECT 1 FROM pg_database WHERE datname=:dbn", {"dbn": dbname})

    if result:
        console.print(f"[yellow]Database '{dbname}' already exists.[/yellow]")
    else:
        await db_admin.execute(f'CREATE DATABASE "{dbname}"')
        console.print(f"[green]Database '{dbname}' created successfully.[/green]")

    await db_admin.disconnect()


__all__ = [
    "createdb",
]
