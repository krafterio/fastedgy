# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from typing import TYPE_CHECKING

from fastapi import Request as FastAPIRequest

from fastedgy.context import set_request, reset_request, set_timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

if TYPE_CHECKING:
    from fastedgy.app import FastEdgy


logger = logging.getLogger("fastedgy.http")


class Request(FastAPIRequest):
    @property
    def app(self) -> "FastEdgy":
        return self.scope["app"]


class ContextRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = set_request(request)

        try:
            return await call_next(request)
        finally:
            reset_request(token)


class TimezoneMiddleware(BaseHTTPMiddleware):
    """Middleware to parse X-Timezone header and set timezone in context."""

    def __init__(self, app: "FastEdgy", header_name: str = "X-Timezone"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next) -> Response:
        timezone_header = request.headers.get(self.header_name)

        if timezone_header:
            try:
                set_timezone(timezone_header)
                logger.debug(
                    f"Set timezone to '{timezone_header}' from {self.header_name} header"
                )
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
