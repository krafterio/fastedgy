# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import shutil
import tempfile

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from fastedgy.app import FastEdgy

from fastedgy.test import database
from fastedgy.test.app import build_app


WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "main")

database.configure_database_env(WORKER_ID)

# A signing key is required for the JWT auth flow exercised by the test app.
os.environ.setdefault("AUTH_SECRET_KEY", "fastedgy-test-secret-key")

# Emails are captured in-memory (no SMTP) and rendered from the bundled test
# templates, so the mail-sending endpoints stay exercisable in tests.
os.environ.setdefault("MAIL_ADAPTER", "mock")
os.environ.setdefault("MAIL_TEMPLATES_PATH", os.path.join(os.path.dirname(__file__), "templates"))

# Each worker gets an isolated storage root under the system temp directory so
# filesystem uploads never collide across parallel pytest-xdist workers. This is
# forced (not setdefault): xdist workers inherit the controller's environment, so
# a default would leak the controller's path into every worker.
STORAGE_ROOT = os.path.join(tempfile.gettempdir(), "fastedgy-test-storage", WORKER_ID)
os.environ["DATA_PATH"] = STORAGE_ROOT


def stored_file_path(relative_path: str) -> str:
    """Absolute on-disk path of a stored file (tests have no workspace, so the "global" prefix)."""
    return os.path.join(STORAGE_ROOT, "global", relative_path)


@pytest.fixture(scope="session", autouse=True)
def cleanup_storage_root() -> Iterator[None]:
    # Each worker owns its storage root, so removing it on teardown is safe under
    # parallel runs and leaves no temporary files behind.
    try:
        yield
    finally:
        shutil.rmtree(STORAGE_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def setup_openapi_app() -> FastEdgy:
    return build_app()


@pytest.fixture(scope="session")
def setup_database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[bool]:
    if not database.can_connect():
        yield False
        return

    shared_dir = tmp_path_factory.getbasetemp().parent if WORKER_ID != "main" else None
    database.ensure_template_database(shared_dir, WORKER_ID)
    database.create_worker_database(WORKER_ID)

    try:
        yield True
    finally:
        database.drop_worker_database(WORKER_ID)


@pytest.fixture(scope="session")
async def setup_app(setup_database: bool) -> AsyncIterator[FastEdgy]:
    if not setup_database:
        pytest.skip("PostgreSQL is not available for integration tests")

    app = build_app()

    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def setup_db(setup_app: FastEdgy) -> FastEdgy:
    """A truncated database for pure service/ORM tests (no HTTP client)."""
    await database.truncate_all_tables()

    return setup_app


@pytest.fixture
async def setup_http(setup_db: FastEdgy) -> AsyncIterator[httpx.AsyncClient]:
    shutil.rmtree(STORAGE_ROOT, ignore_errors=True)

    transport = httpx.ASGITransport(app=setup_db)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as http_client:
        yield http_client


@pytest.fixture
async def auth_http(setup_http: httpx.AsyncClient) -> httpx.AsyncClient:
    """An HTTP client authenticated as a default seeded user.

    Use ``authenticate(client, user)`` from ``fastedgy.test.factories`` to act as
    a specific user instead.
    """
    from fastedgy.test.factories import authenticate, create_user

    user = await create_user(email="auth@example.io")

    return authenticate(setup_http, user)


__all__ = [
    "anyio_backend",
    "setup_openapi_app",
    "setup_database",
    "setup_app",
    "setup_db",
    "setup_http",
    "auth_http",
]
