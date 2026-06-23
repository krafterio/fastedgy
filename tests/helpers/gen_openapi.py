# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from tests.helpers.database import configure_database_env
from tests.helpers.app import SNAPSHOT_PATH, build_app, dump_openapi


def main() -> None:
    configure_database_env("snapshot")

    content = dump_openapi(build_app())

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(content, encoding="utf-8")

    print(f"Wrote {SNAPSHOT_PATH} ({len(content)} bytes)")


if __name__ == "__main__":
    main()


__all__ = [
    "main",
]
