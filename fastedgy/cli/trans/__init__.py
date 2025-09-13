# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import cli


@cli.group()
@cli.initialize_app
def trans():
    """Translation management commands."""
    pass
