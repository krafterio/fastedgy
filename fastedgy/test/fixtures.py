# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import inspect
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
import pytest

from fastedgy.app import FastEdgy
from fastedgy.test import database
from fastedgy.test.app import build_app, load_app

WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "main")

database.configure_database_env(WORKER_ID)

# A signing key is required for the JWT auth flow exercised by the test app.
os.environ.setdefault("AUTH_SECRET_KEY", "fastedgy-test-secret-key")

# Emails are captured in-memory (no SMTP) and rendered from the bundled test
# templates, so the mail-sending endpoints stay exercisable in tests.
os.environ.setdefault("MAIL_ADAPTER", "mock")
# A call site that stores a password unhashed must fail the suite, not be
# repaired silently the way production does.
os.environ.setdefault("STRICT_PASSWORD_HASH", "true")
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

    app = load_app()

    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def seed_data() -> Callable[[], Any] | None:
    """Reference-data seeder run after each truncate.

    Defaults to :func:`fastedgy.orm.loader.load_data`, so a project's
    ``server/data`` records are reloaded before every test exactly as
    ``kt db init-data`` would. A project with no ``data`` directory gets a
    no-op. Override to return another zero-argument callable, or ``None`` to
    skip seeding entirely.
    """
    from fastedgy.orm.loader import load_data

    return load_data


@pytest.fixture(autouse=True)
def fresh_context() -> Iterator[None]:
    """Start every test on an empty request context.

    The request carries the user, the workspace, its membership, the timezone
    and the locale, and the runner shares one contextvar context per worker:
    what a test leaves behind is what the next one reads. That test then runs
    scoped to a workspace it never chose, and its own rows fall out of its own
    queries. The further apart the two tests run, the harder it is to see.

    Autouse, so a suite is covered without asking and no test file carries a
    reset of its own.
    """
    from fastedgy import context

    token = context.set_request(None)

    try:
        yield
    finally:
        context.reset_request(token)


@pytest.fixture
async def setup_db(setup_app: FastEdgy, seed_data: Callable[[], Any] | None) -> FastEdgy:
    """A truncated (then optionally re-seeded) database before each test."""
    await database.truncate_all_tables()

    if seed_data is not None:
        result = seed_data()

        if inspect.isawaitable(result):
            await result

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


@pytest.fixture
def override_settings(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Change application settings for the duration of one test.

    The settings are a DI singleton built once from the env file, so a test
    needing a deployment value the environment does not carry (an encryption
    key, a provider credential) sets it here rather than reaching for the
    service that reads it. The original value is put back when the test ends,
    so nothing leaks into the next one.

    A service caching something derived from a setting has to drop that cache
    itself: this only touches the settings object.

        async def test_x(setup_db, override_settings):
            override_settings(external_calendar_encryption_key="test-key")
    """
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service

    def override(**values: Any) -> None:
        settings = get_service(BaseSettings)

        for name, value in values.items():
            if not hasattr(settings, name):
                raise AttributeError(f"Unknown setting '{name}'")

            monkeypatch.setattr(settings, name, value)

    return override


__all__ = [
    "anyio_backend",
    "auth_http",
    "fresh_context",
    "override_settings",
    "seed_data",
    "setup_app",
    "setup_database",
    "setup_db",
    "setup_http",
    "setup_openapi_app",
]
