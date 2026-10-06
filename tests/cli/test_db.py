# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import rich_click as click

from fastedgy.cli.db import db
from fastedgy.cli.db.init import init


def test_db_init_is_the_fastedgy_one_and_edgy_commands_stay_reachable() -> None:
    ctx = click.Context(db)

    assert db.get_command(ctx, "init") is init
    assert db.get_command(ctx, "migrate") is not None
    assert db.get_command(ctx, "makemigrations") is not None
