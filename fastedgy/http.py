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
    "TimezoneMiddleware",
]
