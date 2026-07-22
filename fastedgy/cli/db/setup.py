# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
import os

from contextlib import redirect_stderr, redirect_stdout
from glob import glob

import edgy
import rich_click as click

from fastedgy import cli
from fastedgy.cli import CliContext, console
from fastedgy.cli.db import db
from fastedgy.config import BaseSettings


def _invoke(ctx: click.Context, command: click.Command, args: list[str] | None = None) -> None:
    sub_ctx = command.make_context(command.name, list(args or []), parent=ctx)

    with sub_ctx:
        command.invoke(sub_ctx)


def _invoke_quietly(ctx: click.Context, command: click.Command, args: list[str] | None = None) -> None:
    buffer = io.StringIO()

    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            _invoke(ctx, command, args)
    except BaseException:
        output = buffer.getvalue()

        if output:
            console.print(output, markup=False, highlight=False)

        raise


def _get_group_command(ctx: click.Context, name: str) -> click.Command:
    command = db.get_command(ctx, name)

    if command is None:
        raise cli.ClickException(f"The '{name}' command is not available.")

    return command


@db.command()
@cli.pass_context
def setup(ctx: cli.Context):
    """Set up the database: create it, apply migrations and load init-data."""
    from fastedgy.cli.db.createdb import createdb
    from fastedgy.cli.db.init import init
    from fastedgy.cli.db.init_data import init_data

    cli_ctx: CliContext = ctx.obj
    settings = cli_ctx.get(BaseSettings)
    directory = os.path.join(settings.server_path, str(edgy.monkay.settings.migration_directory))
    has_repo = os.path.isfile(os.path.join(directory, "alembic.ini"))
    has_revisions = any(
        not os.path.basename(path).startswith("_") for path in glob(os.path.join(directory, "versions", "*.py"))
    )

    _invoke(ctx, createdb)

    if not has_repo:
        _invoke_quietly(ctx, init)
        console.print("[green]Migration repository initialized.[/green]")

    if not has_revisions:
        _invoke_quietly(ctx, _get_group_command(ctx, "makemigrations"), ["-m", "init project"])
        console.print("[green]Initial migration generated.[/green]")

    _invoke_quietly(ctx, _get_group_command(ctx, "migrate"))
    console.print("[green]Database migrated.[/green]")

    _invoke(ctx, init_data)


__all__ = [
    "setup",
]
