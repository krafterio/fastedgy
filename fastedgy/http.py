# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING

from fastapi import Request as FastAPIRequest

from fastedgy.context import set_request, reset_request

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from fastedgy.app import FastEdgy


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


__all__ = [
    "Request",
    "ContextRequestMiddleware",
]
