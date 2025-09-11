# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import edgy
from pathlib import Path

from alembic import command
from edgy.cli.base import Config
from edgy.cli.decorators import add_migration_directory_option
from fastedgy import cli
from fastedgy.cli import CliContext
from fastedgy.cli.db import db


FASTEDGY_TEMPLATE_NAME = "fastedgy"
FASTEDGY_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


@add_migration_directory_option
@db.command()
@cli.option(
    "-t", "--template", default=None, help=('Repository template to use (default is "fastedgy")')
)
@cli.option(
    "--package",
    is_flag=True,
    help=("Write empty __init__.py files to the environment and version locations"),
)
@cli.pass_cli_context
async def init(ctx: CliContext, template: str | None, package: bool):
    """Creates a new migration repository."""
    directory = str(edgy.monkay.settings.migration_directory)

    template_directory = None

    if template is not None and ("/" in template or "\\" in template):
        template_directory, template = os.path.split(template)

    if template is None:
        template = FASTEDGY_TEMPLATE_NAME
        template_directory = str(FASTEDGY_TEMPLATE_DIR)
    elif template == FASTEDGY_TEMPLATE_NAME and template_directory is None:
        template_directory = str(FASTEDGY_TEMPLATE_DIR)

    config = Config(template_directory=template_directory)
    config.set_main_option("script_location", directory)
    config.config_file_name = os.path.join(directory, "alembic.ini")

    command.init(config, directory, template, package)
