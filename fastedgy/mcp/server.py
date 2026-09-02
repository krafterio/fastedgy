# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The MCP server of a FastEdgy app, over the stateless Streamable HTTP
transport: no handshake, no session, any worker answers any call."""

import json
from collections.abc import Iterable, Mapping
from typing import Any

from fastapi import HTTPException
from mcp import types
from mcp.server.caching import CacheableMethod, CacheHint
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import MCPError
from starlette.types import Receive, Scope, Send

from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.depends.security import find_workspace_user_model
from fastedgy.mcp.registry import McpRegistry
from fastedgy.mcp.tools import (
    BUILTIN_TOOL_NAMES,
    call_tool,
    get_tools,
    model_resource_uri,
    models_resource_uri,
    read_resource,
)

DEFAULT_INSTRUCTIONS = (
    "Tools over one deployment of this API, with the rights of the key's owner. "
    "Call `list_models` then `get_model_info` before the first read or write on a model, and never "
    "guess a field name or a filter operator. `list_records` is the only source on records: never "
    "describe a record you have not read. `create_record`, `update_record` and `delete_record` apply "
    "immediately and cannot be undone, so only write what the user actually asked for, and pass only "
    "the fields that change on an update."
)

# A tool result is never cacheable, only these six methods are: the catalogue is
# the same for every caller, a model's metadata is not (a workspace extends it
# with its own fields), so it stays private and short-lived.
DEFAULT_CACHE_HINTS: dict[CacheableMethod, CacheHint] = {
    "tools/list": CacheHint(ttl_ms=3_600_000, scope="public"),
    "resources/templates/list": CacheHint(ttl_ms=3_600_000, scope="public"),
    "resources/read": CacheHint(ttl_ms=300_000, scope="private"),
}


def _list_tools_handler(disabled: frozenset[str]):
    async def _on_list_tools(
        ctx: ServerRequestContext[Any],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        tools = [tool for tool in await get_tools() if tool["name"] not in disabled]

        return types.ListToolsResult(tools=[types.Tool(**tool) for tool in tools])

    return _on_list_tools


def _require_request():
    request = context.get_request()

    if request is None:
        raise RuntimeError("The MCP transport runs outside of a request")

    return request


def _call_tool_handler(disabled: frozenset[str]):
    async def _on_call_tool(
        ctx: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        request = _require_request()

        # A tool kept out of the catalogue is not callable either: a client may
        # be working from a cached `tools/list`.
        if params.name in disabled:
            raise MCPError(types.INVALID_PARAMS, f"Unknown tool '{params.name}'")

        try:
            content = await call_tool(request, params.name, params.arguments or {})
        except HTTPException as e:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"HTTP {e.status_code}: {e.detail}")],
                is_error=True,
            )

        return types.CallToolResult(content=content)

    return _on_call_tool


async def _on_list_resource_templates(
    ctx: ServerRequestContext[Any],
    params: types.PaginatedRequestParams | None,
) -> types.ListResourceTemplatesResult:
    workspaced = find_workspace_user_model() is not None

    workspace = "{workspace}" if workspaced else None

    return types.ListResourceTemplatesResult(
        resource_templates=[
            types.ResourceTemplate(
                name="models",
                title="Model catalogue",
                uri_template=models_resource_uri(workspace),
                description="Every model this API exposes: name, API plural and label.",
                mime_type="application/json",
            ),
            types.ResourceTemplate(
                name="model",
                title="Model metadata",
                uri_template=model_resource_uri("{model}", workspace),
                description="Fields, types, filter operators and filter syntax of one model.",
                mime_type="application/json",
            ),
            *(
                types.ResourceTemplate(
                    name=resource.name,
                    title=resource.title,
                    uri_template=resource.uri_template,
                    description=resource.description,
                    mime_type=resource.mime_type,
                )
                for resource in get_service(McpRegistry).get_resources()
            ),
        ]
    )


async def _on_read_resource(
    ctx: ServerRequestContext[Any],
    params: types.ReadResourceRequestParams,
) -> types.ReadResourceResult:
    _require_request()

    try:
        payload = await read_resource(params.uri)
    except HTTPException as e:
        # A bare exception reaches the client as "Internal server error": the
        # refusal has to travel as a JSON-RPC error to say anything at all.
        code = types.INVALID_PARAMS if e.status_code < 500 else types.INTERNAL_ERROR

        raise MCPError(code, f"HTTP {e.status_code}: {e.detail}") from e

    return types.ReadResourceResult(
        contents=[
            types.TextResourceContents(
                uri=params.uri,
                mime_type="application/json",
                text=json.dumps(payload, ensure_ascii=False, default=str),
            )
        ]
    )


def normalize_disabled_tools(disabled_tools: Iterable[str] | None) -> frozenset[str]:
    """A name that matches nothing would silently keep the tool: refuse it at
    wiring time rather than let it pass for a working opt-out."""
    disabled = frozenset(disabled_tools or ())
    unknown = sorted(disabled - BUILTIN_TOOL_NAMES)

    if unknown:
        raise ValueError(
            f"Unknown built-in MCP tool(s) in disabled_tools: {', '.join(unknown)}. "
            f"Known: {', '.join(sorted(BUILTIN_TOOL_NAMES))}."
        )

    return disabled


def build_mcp_server(
    name: str | None = None,
    instructions: str | None = None,
    cache_hints: Mapping[CacheableMethod, CacheHint] | None = None,
    disabled_tools: Iterable[str] | None = None,
) -> Server:
    disabled = normalize_disabled_tools(disabled_tools)

    return Server(
        name or get_service(BaseSettings).title,
        instructions=instructions or DEFAULT_INSTRUCTIONS,
        cache_hints=dict(cache_hints) if cache_hints is not None else DEFAULT_CACHE_HINTS,
        on_list_tools=_list_tools_handler(disabled),
        on_call_tool=_call_tool_handler(disabled),
        on_list_resource_templates=_on_list_resource_templates,
        on_read_resource=_on_read_resource,
    )


class McpTransport:
    """One session manager per request (~70 µs): it accepts a single `run()` in
    its life, and its anyio cancel scope must be left by the task that entered
    it. The server itself is built once, on the first call, because its default
    name comes from the settings."""

    def __init__(
        self,
        name: str | None = None,
        instructions: str | None = None,
        cache_hints: Mapping[CacheableMethod, CacheHint] | None = None,
        disabled_tools: Iterable[str] | None = None,
    ) -> None:
        self._name = name
        self._instructions = instructions
        self._cache_hints = cache_hints
        # Validated now rather than on the first call, so a typo fails at wiring.
        self._disabled_tools = normalize_disabled_tools(disabled_tools)
        self._server: Server | None = None

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._server is None:
            self._server = build_mcp_server(self._name, self._instructions, self._cache_hints, self._disabled_tools)

        manager = StreamableHTTPSessionManager(app=self._server, json_response=True, stateless=True)

        async with manager.run():
            await manager.handle_request(scope, receive, send)


__all__ = [
    "DEFAULT_CACHE_HINTS",
    "DEFAULT_INSTRUCTIONS",
    "McpTransport",
    "build_mcp_server",
    "normalize_disabled_tools",
]
