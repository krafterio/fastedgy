# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import tempfile

from fastedgy.test import database


def _run_migrations() -> None:
    import edgy

    from alembic import command
    from edgy.cli.base import Config, revision, upgrade
    from fastedgy.cli.db.init import FASTEDGY_TEMPLATE_DIR, FASTEDGY_TEMPLATE_NAME

    migrations_dir = tempfile.mkdtemp(prefix="fastedgy-test-migrations-")

    config = Config(template_directory=str(FASTEDGY_TEMPLATE_DIR))
    config.set_main_option("script_location", migrations_dir)
    config.config_file_name = os.path.join(migrations_dir, "alembic.ini")
    command.init(config, migrations_dir, FASTEDGY_TEMPLATE_NAME, False)

    edgy.monkay.settings.migration_directory = migrations_dir

    revision(autogenerate=True, message="test schema")
    upgrade("head")


def main() -> None:
    os.environ["FASTEDGY_TEST_ACTIVE"] = "1"
    os.environ["DATABASE_URL"] = database.template_database_url()

    database.recreate_template_database()

    from fastedgy.test.app import build_app

    build_app()
    _run_migrations()


if __name__ == "__main__":
    main()


__all__ = [
    "main",
]
