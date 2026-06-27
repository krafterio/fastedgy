# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import tempfile

from fastedgy.test import database


def _has_committed_migrations() -> bool:
    """True when the app under test ships its own Alembic migration scripts."""
    try:
        from alembic.script import ScriptDirectory
        from edgy.cli.base import Config

        script = ScriptDirectory.from_config(Config.get_instance())

        return next(iter(script.walk_revisions()), None) is not None
    except Exception:
        return False


def _autogenerate_schema() -> None:
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


def _build_schema() -> None:
    # A project ships committed migrations: apply them so the template reproduces
    # its real schema (table ordering, circular FKs, raw views). The synthetic
    # test app has none, so fall back to autogenerating one from the models.
    if _has_committed_migrations():
        from edgy.cli.base import upgrade

        upgrade("head")
    else:
        _autogenerate_schema()


def main() -> None:
    os.environ["FASTEDGY_TEST_ACTIVE"] = "1"
    os.environ["DATABASE_URL"] = database.template_database_url()

    database.recreate_template_database()

    from fastedgy.test.app import load_app

    load_app()
    _build_schema()


if __name__ == "__main__":
    main()


__all__ = [
    "main",
]
