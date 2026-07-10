# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from starlette.requests import ClientDisconnect

from fastedgy.app import FastEdgy


async def test_client_disconnect_ends_the_request_quietly(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient, caplog
) -> None:
    async def vanishing_upload() -> None:
        # Simulates starlette raising ClientDisconnect while the endpoint
        # reads the request body (request.form(), request.json(), ...).
        raise ClientDisconnect()

    setup_db.add_api_route("/api/test-client-disconnect", vanishing_upload, methods=["POST"])

    response = await setup_http.post("/api/test-client-disconnect")

    assert response.status_code == 499
    assert not any(r.levelno >= 40 for r in caplog.records)


async def test_database_unavailable_answers_503_maintenance(setup_db: FastEdgy, setup_http: httpx.AsyncClient) -> None:
    from asyncpg.exceptions import ConnectionDoesNotExistError
    from sqlalchemy.exc import OperationalError

    async def dead_database() -> None:
        # sqlalchemy wraps the driver error as a DBAPI error with __cause__,
        # exactly what a request hitting a restarting postgres sees.
        raise OperationalError("SELECT 1", {}, ConnectionDoesNotExistError("connection was closed"))

    setup_db.add_api_route("/api/test-db-down", dead_database, methods=["GET"])

    response = await setup_http.get("/api/test-db-down")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"


async def test_connection_refused_answers_503_maintenance(setup_db: FastEdgy, setup_http: httpx.AsyncClient) -> None:
    from sqlalchemy.exc import OperationalError

    async def refused_database() -> None:
        raise OperationalError("SELECT 1", {}, ConnectionRefusedError(61, "Connection refused"))

    setup_db.add_api_route("/api/test-db-refused", refused_database, methods=["GET"])

    assert (await setup_http.get("/api/test-db-refused")).status_code == 503


async def test_query_errors_on_a_healthy_database_stay_errors(
    setup_db: FastEdgy, setup_http: httpx.AsyncClient
) -> None:
    # The test transport propagates unhandled exceptions (in production the
    # ServerErrorMiddleware turns them into a 500): a propagated exception
    # proves the middleware did NOT swallow it into a 503.
    import pytest

    from asyncpg.exceptions import InterfaceError, QueryCanceledError, UniqueViolationError
    from sqlalchemy.exc import IntegrityError, OperationalError

    async def constraint_violation() -> None:
        raise IntegrityError("INSERT ...", {}, UniqueViolationError("duplicate key"))

    async def statement_timeout() -> None:
        raise OperationalError("SELECT ...", {}, QueryCanceledError("canceling statement due to statement timeout"))

    async def pool_misuse() -> None:
        raise InterfaceError("cannot call fetch(): connection has been released back to the pool")

    setup_db.add_api_route("/api/test-constraint", constraint_violation, methods=["GET"])
    setup_db.add_api_route("/api/test-timeout", statement_timeout, methods=["GET"])
    setup_db.add_api_route("/api/test-pool-misuse", pool_misuse, methods=["GET"])

    with pytest.raises(IntegrityError):
        await setup_http.get("/api/test-constraint")
    with pytest.raises(OperationalError):
        await setup_http.get("/api/test-timeout")
    with pytest.raises(InterfaceError):
        await setup_http.get("/api/test-pool-misuse")
