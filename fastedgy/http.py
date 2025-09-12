# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from starlette.middleware.base import BaseHTTPMiddleware
from fastedgy.context import set_request, reset_request


class ContextRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = set_request(request)

        try:
            return await call_next(request)
        finally:
            reset_request(token)


__all__ = [
    "ContextRequestMiddleware",
]
