# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import cli

import fastedgy.orm.migration  # noqa: F401


@cli.group(name="db")
def db():
    """Database management commands."""
    pass


cli.register_commands_in_group(
    "edgy.cli.operations",
    db,
    decorators=[
        cli.initialize_app,
        cli.lifespan,
    ],
)

# Register fulltext-reindex command
from fastedgy.cli.db.fulltext import fulltext_reindex

db.add_command(fulltext_reindex)


__all__ = [
    "db",
]
