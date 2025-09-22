# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import cli

import fastedgy.orm.migration  # noqa: F401


@cli.group(name="db")
@cli.lifespan
def db():
    """Database management commands."""
    pass


cli.register_commands_in_group("edgy.cli.operations", db)


__all__ = [
    "db",
]
