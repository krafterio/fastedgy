# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import cli


@cli.command(name="init-data")
@cli.initialize_app
@cli.lifespan
async def init_data():
    """Load init-data from the server ``data`` directory (create or update)."""
    from fastedgy.cli import console
    from fastedgy.orm.loader import load_data

    report = await load_data()

    console.print(f"[green]Init data loaded: {report.created} created, {report.updated} updated[/green]")


__all__ = [
    "init_data",
]
