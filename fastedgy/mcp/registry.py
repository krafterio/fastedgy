# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""What an application adds to the MCP server of its own.

Registration is additive: the built-in tools and resources always answer, and a
name that collides with one is refused rather than silently shadowing it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastedgy.dependencies import get_service

type ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]
"""Takes the call arguments, gives back either a value to serialize as JSON or
a ready list of MCP content blocks."""

type ResourceReader = Callable[[str], Awaitable[Any]]
"""Takes the whole URI, gives back the value to serialize as JSON."""


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


@dataclass(frozen=True)
class McpResource:
    name: str
    uri_template: str
    reader: ResourceReader
    description: str = ""
    mime_type: str = "application/json"
    title: str | None = None

    @property
    def prefix(self) -> str:
        """Everything before the first placeholder: what a concrete URI has to
        start with to belong to this resource."""
        head, _, _ = self.uri_template.partition("{")

        return head


@dataclass
class McpRegistry:
    """The tools and resources an application adds to the MCP server."""

    _tools: dict[str, McpTool] = field(default_factory=dict)
    _resources: dict[str, McpResource] = field(default_factory=dict)

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ) -> McpTool:
        from fastedgy.mcp.tools import BUILTIN_TOOL_NAMES

        if name in BUILTIN_TOOL_NAMES or name in self._tools:
            raise ValueError(f"An MCP tool named '{name}' is already registered")

        tool = McpTool(name=name, description=description, input_schema=input_schema, handler=handler)
        self._tools[name] = tool

        return tool

    def register_resource(
        self,
        name: str,
        uri_template: str,
        reader: ResourceReader,
        description: str = "",
        mime_type: str = "application/json",
        title: str | None = None,
    ) -> McpResource:
        from fastedgy.mcp.tools import BUILTIN_RESOURCE_PREFIXES

        resource = McpResource(
            name=name,
            uri_template=uri_template,
            reader=reader,
            description=description,
            mime_type=mime_type,
            title=title,
        )

        if name in self._resources:
            raise ValueError(f"An MCP resource named '{name}' is already registered")

        if any(resource.prefix.startswith(prefix) for prefix in BUILTIN_RESOURCE_PREFIXES):
            raise ValueError(f"The URI template '{uri_template}' collides with a built-in resource")

        self._resources[name] = resource

        return resource

    def get_tools(self) -> list[McpTool]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> McpTool | None:
        return self._tools.get(name)

    def get_resources(self) -> list[McpResource]:
        return list(self._resources.values())

    def find_resource(self, uri: str) -> McpResource | None:
        """The resource whose prefix the URI matches, longest first: a template
        may sit under another one's namespace."""
        matches = [resource for resource in self._resources.values() if uri.startswith(resource.prefix)]

        return max(matches, key=lambda resource: len(resource.prefix)) if matches else None


def mcp_tool(name: str, description: str, input_schema: dict[str, Any]) -> Callable[[ToolHandler], ToolHandler]:
    """Register an async function as an MCP tool.

    The module holding it has to be imported by the time the app is built, the
    way a view transformer's is.

        @mcp_tool("search_flows", description="…", input_schema={...})
        async def search_flows(arguments: dict) -> list[dict]:
            ...
    """

    def decorator(handler: ToolHandler) -> ToolHandler:
        get_service(McpRegistry).register_tool(name, description, input_schema, handler)

        return handler

    return decorator


def mcp_resource(
    name: str,
    uri_template: str,
    description: str = "",
    mime_type: str = "application/json",
    title: str | None = None,
) -> Callable[[ResourceReader], ResourceReader]:
    """Register an async function as an MCP resource, read by its whole URI."""

    def decorator(reader: ResourceReader) -> ResourceReader:
        get_service(McpRegistry).register_resource(name, uri_template, reader, description, mime_type, title)

        return reader

    return decorator


__all__ = [
    "McpRegistry",
    "McpResource",
    "McpTool",
    "ResourceReader",
    "ToolHandler",
    "mcp_resource",
    "mcp_tool",
]
