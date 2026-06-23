# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from fastedgy.app import FastEdgy

from tests.helpers import database
from tests.helpers.app import build_app


WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "main")

database.configure_database_env(WORKER_ID)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def openapi_app() -> FastEdgy:
    return build_app()


@pytest.fixture(scope="session")
def integration_database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[bool]:
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
async def integration_app(integration_database: bool) -> AsyncIterator[FastEdgy]:
    if not integration_database:
        pytest.skip("PostgreSQL is not available for integration tests")

    app = build_app()

    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(integration_app: FastEdgy) -> AsyncIterator[httpx.AsyncClient]:
    await database.truncate_all_tables()

    transport = httpx.ASGITransport(app=integration_app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as http_client:
        yield http_client
