# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
import os
import subprocess
import sys
import time

from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine.url import make_url


DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/fastedgy"
TEST_DATABASE_SUFFIX = "-test"

_PROJECT_ROOT = Path.cwd()


def _resolve_base_database_url() -> str:
    env_url = os.environ.get("FASTEDGY_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

    if env_url and "FASTEDGY_TEST_ACTIVE" not in os.environ:
        return env_url

    env_file = _PROJECT_ROOT / ".env"

    if env_file.exists():
        dotenv_url = dotenv_values(env_file).get("DATABASE_URL")

        if dotenv_url:
            return dotenv_url

    return DEFAULT_DATABASE_URL


def _base_test_database_name() -> str:
    name = make_url(_resolve_base_database_url()).database or "fastedgy"

    if not name.endswith(TEST_DATABASE_SUFFIX):
        name = f"{name}{TEST_DATABASE_SUFFIX}"

    return name


def _url_for(database_name: str) -> str:
    return make_url(_resolve_base_database_url()).set(database=database_name).render_as_string(hide_password=False)


def template_database_name() -> str:
    return f"{_base_test_database_name()}-tpl"


def _worker_suffix(worker_id: str) -> str:
    if not worker_id or worker_id == "main":
        return ""

    digits = "".join(char for char in worker_id if char.isdigit())

    return f"-{int(digits) + 1}" if digits else f"-{worker_id}"


def worker_database_name(worker_id: str) -> str:
    return f"{_base_test_database_name()}{_worker_suffix(worker_id)}"


def template_database_url() -> str:
    return _url_for(template_database_name())


def worker_database_url(worker_id: str) -> str:
    return _url_for(worker_database_name(worker_id))


def admin_database_url() -> str:
    return _url_for("postgres")


def configure_database_env(worker_id: str) -> str:
    url = worker_database_url(worker_id)
    os.environ["FASTEDGY_TEST_ACTIVE"] = "1"
    os.environ["DATABASE_URL"] = url

    return url


async def _terminate_connections(admin, database_name: str) -> None:
    await admin.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name AND pid <> pg_backend_pid()",
        {"name": database_name},
    )


async def _recreate_database(database_name: str) -> None:
    from fastedgy.orm import Database

    admin = Database(admin_database_url())
    await admin.connect()

    try:
        await _terminate_connections(admin, database_name)
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await admin.disconnect()


async def _clone_database(database_name: str, template_name: str) -> None:
    from fastedgy.orm import Database

    admin = Database(admin_database_url())
    await admin.connect()

    try:
        await _terminate_connections(admin, template_name)
        await _terminate_connections(admin, database_name)
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.execute(f'CREATE DATABASE "{database_name}" TEMPLATE "{template_name}"')
    finally:
        await admin.disconnect()


async def _drop_database(database_name: str) -> None:
    from fastedgy.orm import Database

    admin = Database(admin_database_url())
    await admin.connect()

    try:
        await _terminate_connections(admin, database_name)
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await admin.disconnect()


async def _can_connect() -> bool:
    from fastedgy.orm import Database

    admin = Database(admin_database_url())

    try:
        await admin.connect()
    except Exception:
        return False

    await admin.disconnect()

    return True


def can_connect() -> bool:
    return asyncio.run(_can_connect())


def recreate_template_database() -> None:
    asyncio.run(_recreate_database(template_database_name()))


def create_worker_database(worker_id: str) -> None:
    asyncio.run(_clone_database(worker_database_name(worker_id), template_database_name()))


def drop_worker_database(worker_id: str) -> None:
    asyncio.run(_drop_database(worker_database_name(worker_id)))


def _build_template_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fastedgy.test.build_template"],
        cwd=str(_PROJECT_ROOT),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to build the migrated template database:\nstdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )


def _wait_for_marker(marker: Path, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if marker.exists():
            if marker.read_text(encoding="utf-8").strip() == "ok":
                return

            raise RuntimeError("Template database build failed in another worker")

        time.sleep(0.5)

    raise TimeoutError("Timed out waiting for the template database to be built")


def ensure_template_database(shared_dir: Path | None, worker_id: str) -> None:
    if worker_id == "main" or shared_dir is None:
        _build_template_subprocess()
        return

    ready = shared_dir / f"{template_database_name()}.ready"
    lock = shared_dir / f"{template_database_name()}.lock"

    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        _wait_for_marker(ready)
        return

    try:
        _build_template_subprocess()
        ready.write_text("ok", encoding="utf-8")
    except Exception:
        ready.write_text("failed", encoding="utf-8")
        raise
    finally:
        os.close(fd)


async def truncate_all_tables() -> None:
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry

    registry = get_service(Registry)
    tables = [table.name for table in registry.metadata_by_name[None].sorted_tables if table.name != "alembic_version"]

    if not tables:
        return

    quoted = ", ".join(f'"{name}"' for name in tables)
    await registry.database.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")


__all__ = [
    "DEFAULT_DATABASE_URL",
    "TEST_DATABASE_SUFFIX",
    "template_database_name",
    "worker_database_name",
    "template_database_url",
    "worker_database_url",
    "admin_database_url",
    "configure_database_env",
    "can_connect",
    "recreate_template_database",
    "create_worker_database",
    "drop_worker_database",
    "ensure_template_database",
    "truncate_all_tables",
]
