# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

import rich_click as click

from fastedgy import cli
from fastedgy.cli.db.fulltext import fulltext_reindex


class LazyDbGroup(cli.Group):
    """The ``db`` group registers Edgy's migration commands (which pull Alembic)
    only when the group is actually used, so unrelated commands such as ``serve``
    never import Alembic.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._operations_loaded = False

    def _ensure_operations(self) -> None:
        if self._operations_loaded:
            return

        self._operations_loaded = True
        cli.register_commands_in_group(
            "edgy.cli.operations",
            self,
            decorators=[
                cli.initialize_app,
                cli.lifespan,
            ],
        )

    def list_commands(self, ctx: cli.Context) -> list[str]:
        self._ensure_operations()
        return super().list_commands(ctx)

    def get_command(self, ctx: cli.Context, cmd_name: str) -> click.Command | None:
        self._ensure_operations()
        return super().get_command(ctx, cmd_name)


@cli.group(name="db", cls=LazyDbGroup)
def db():
    """Database management commands."""
    pass


db.add_command(fulltext_reindex)


__all__ = [
    "db",
]
