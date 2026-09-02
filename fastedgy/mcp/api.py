# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""HTTP entry of the MCP transport."""

from collections.abc import Iterable, Mapping

from fastapi import APIRouter, Depends
from mcp.server.caching import CacheableMethod, CacheHint
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from fastedgy import context
from fastedgy.http import Request
from fastedgy.mcp.server import McpTransport


class McpResponse(Response):
    """The transport writes on the ASGI channel itself: the route hands it over
    instead of rendering a response. The request context is re-installed here
    because the tools run past the dependency's scope."""

    def __init__(self, transport: McpTransport, user) -> None:
        super().__init__()
        self.transport = transport
        self.user = user

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_token = context.set_request(Request(scope))
        context.set_user(self.user)

        try:
            await self.transport.handle(scope, receive, send)
        finally:
            context.reset_request(request_token)


def create_mcp_router(
    name: str | None = None,
    instructions: str | None = None,
    path: str = "/mcp",
    cache_hints: Mapping[CacheableMethod, CacheHint] | None = None,
    disabled_tools: Iterable[str] | None = None,
) -> APIRouter:
    """The MCP endpoint, authenticated like every other route: a personal API
    key or a JWT in the `Authorization` header.

    `cache_hints` overrides `DEFAULT_CACHE_HINTS` wholesale, for an app that
    wants a different lifetime on the cacheable methods. `disabled_tools` names
    the built-in tools this deployment does not expose.
    """
    from fastedgy.depends.security import get_current_user
    from fastedgy.models.user_api_token import find_user_api_token_model

    if find_user_api_token_model() is None:
        # A JWT expires in minutes; a machine client needs a key that does not.
        # Without one the endpoint would be there and unreachable.
        raise RuntimeError(
            "The MCP server needs personal API keys: build the application with `FastEdgy(user_api_tokens=True)`."
        )

    transport = McpTransport(name, instructions, cache_hints, disabled_tools)
    router = APIRouter(tags=["mcp"])

    @router.api_route(path, methods=["GET", "POST", "DELETE"], include_in_schema=False)
    async def mcp(user=Depends(get_current_user)) -> Response:
        return McpResponse(transport, user)

    return router


__all__ = [
    "McpResponse",
    "create_mcp_router",
]
