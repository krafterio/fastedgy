# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

try:
    import mcp.server  # noqa: F401
except ModuleNotFoundError as e:  # pragma: no cover - depends on the install
    raise ImportError("The MCP server needs the optional `mcp` dependency: install `fastedgy[mcp]`.") from e

from fastedgy.mcp.api import McpResponse, create_mcp_router
from fastedgy.mcp.registry import (
    McpRegistry,
    McpResource,
    McpTool,
    mcp_resource,
    mcp_tool,
)
from fastedgy.mcp.server import (
    DEFAULT_CACHE_HINTS,
    DEFAULT_INSTRUCTIONS,
    McpTransport,
    build_mcp_server,
)
from fastedgy.mcp.tools import enter_workspace

__all__ = [
    "DEFAULT_CACHE_HINTS",
    "DEFAULT_INSTRUCTIONS",
    "McpRegistry",
    "McpResource",
    "McpResponse",
    "McpTool",
    "McpTransport",
    "build_mcp_server",
    "create_mcp_router",
    "enter_workspace",
    "mcp_resource",
    "mcp_tool",
]
