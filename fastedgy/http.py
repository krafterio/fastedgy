# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from typing import TYPE_CHECKING, cast

from fastapi import Request as FastAPIRequest

from fastedgy.context import set_request, reset_request, set_timezone
from fastedgy.timezone import get_timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
from starlette.responses import Response
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from fastedgy.app import FastEdgy


logger = logging.getLogger("fastedgy.http")


class Request(FastAPIRequest):
    @property
    def app(self) -> "FastEdgy":
        return self.scope["app"]


def is_database_unavailable(exc: BaseException) -> bool:
    """True when the exception chain shows the DATABASE ITSELF is unreachable
    — connection refused, killed or closing (restart, failover) — as opposed
    to a query failing on a healthy database (constraint violation, bad SQL,
    statement timeout), which must keep surfacing as a plain 500.
    """
    from asyncpg.exceptions import (
        AdminShutdownError,
        CannotConnectNowError,
        CrashShutdownError,
        InterfaceError as AsyncpgInterfaceError,
        PostgresConnectionError,
    )
    from sqlalchemy.exc import DBAPIError

    def _links(err: BaseException) -> list[BaseException]:
        chained = [err.__cause__, err.__context__]
        # sqlalchemy stores the driver error on .orig; depending on the code
        # path it is not always chained as __cause__.
        orig = getattr(err, "orig", None)
        if isinstance(orig, BaseException):
            chained.append(orig)
        return [c for c in chained if c is not None]

    dbapi_seen = False
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        e = stack.pop()
        if id(e) in seen:
            continue
        seen.add(id(e))
        # 08-class (connection exception) + the operator-intervention members
        # that mean "the server is going away / not up yet". QueryCanceled
        # (statement_timeout, same 57 class) is deliberately NOT included.
        if isinstance(e, (PostgresConnectionError, CannotConnectNowError, AdminShutdownError, CrashShutdownError)):
            return True
        # Client-side interface errors cover both dead connections ("the
        # connection is closed") and pool misuse bugs ("released back to the
        # pool", "another operation is in progress"): only the former is a
        # database outage.
        if isinstance(e, AsyncpgInterfaceError) and "closed" in str(e):
            return True
        if isinstance(e, DBAPIError):
            dbapi_seen = True
        elif isinstance(e, OSError) and dbapi_seen:
            # A raw socket error (connection refused/reset) chained under a
            # DBAPI error is the driver failing to reach the server. Bare
            # OSErrors without that context (external HTTP calls...) are not.
            return True
        stack.extend(_links(e))
    return False


class DatabaseUnavailableMiddleware(BaseHTTPMiddleware):
    """Answer 503 Service Unavailable while the database is unreachable.

    A database restart (planned maintenance, failover) otherwise surfaces as
    uncaught 500s: clients show a generic server-error screen and every
    in-flight request logs an error-level traceback for a condition that is
    transient and expected. A 503 with Retry-After is the contract clients
    already understand as "maintenance, retry shortly" (nginx emits the same
    for an unreachable upstream), and the log level is warning because the
    condition is operational, not a code failure.
    """

    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            if not is_database_unavailable(e):
                raise
            logger.warning(f"Database unavailable, answering 503 maintenance: {e!r}")
            return Response(status_code=503, headers={"Retry-After": "5"})


class ContextRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = set_request(cast(Request, request))

        try:
            return await call_next(request)
        except ClientDisconnect:
            # The client hung up while its request body was being read
            # (mobile network drop, app closed mid-upload): nothing failed
            # server-side and there is nobody left to answer. An empty 499
            # (nginx's "client closed request") ends the ASGI cycle cleanly
            # instead of letting uvicorn log an error traceback.
            return Response(status_code=499)
        finally:
            reset_request(token)


class TimezoneMiddleware(BaseHTTPMiddleware):
    """Middleware to parse X-Timezone header and set timezone in context."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Timezone"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: FastAPIRequest, call_next) -> Response:
        timezone_header = request.headers.get(self.header_name)

        if timezone_header:
            try:
                if isinstance(timezone_header, str) and timezone_header.lower() == "system":
                    timezone_header = get_timezone()

                set_timezone(timezone_header)
                logger.debug(f"Set timezone to '{timezone_header}' from {self.header_name} header")
            except Exception as e:
                logger.debug(
                    f"Invalid timezone '{timezone_header}' in {self.header_name} header: {e}. "
                    "Using server default timezone."
                )

        return await call_next(request)


__all__ = [
    "Request",
    "ContextRequestMiddleware",
    "DatabaseUnavailableMiddleware",
    "TimezoneMiddleware",
    "is_database_unavailable",
]
