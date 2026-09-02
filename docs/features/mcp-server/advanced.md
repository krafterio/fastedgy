# MCP Server - Advanced usage

## Adding your own tools

A tool is an async function taking the call arguments and giving back what to serialize. Register it with the
`@mcp_tool` decorator, from a module the application imports at startup, the way a view transformer is registered:

```python
from fastedgy.mcp import enter_workspace, mcp_tool
from fastedgy.orm.filter import R
from models.flow import Flow


@mcp_tool(
    "close_flow",
    description="Closes a flow and records why. Applies immediately.",
    input_schema={
        "type": "object",
        "properties": {
            "workspace": {"type": "string"},
            "reference": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["workspace", "reference", "reason"],
    },
)
async def close_flow(arguments: dict) -> dict:
    await enter_workspace(arguments["workspace"])

    flow = await Flow.query.filter(R("reference", "=", arguments["reference"])).get()
    flow.closed_reason = arguments["reason"]
    await flow.save()

    return {"reference": flow.reference, "closed": True}
```

`enter_workspace(slug, required=True)` runs the rest of the call as that workspace and refuses a slug the caller is not
a member of, exactly as the built-in tools do. Skip it in an application without workspaces.

The return value is serialized as JSON. A handler that needs control builds its own MCP content blocks and returns them
as a list instead.

The registry is also reachable as a service, for a tool built at runtime:

```python
from fastedgy.dependencies import get_service
from fastedgy.mcp import McpRegistry

get_service(McpRegistry).register_tool("close_flow", description="…", input_schema={...}, handler=close_flow)
```

## Adding your own resources

A resource is read by its whole URI, and the reader parses it. Registration takes a URI template, which is what
`resources/templates/list` advertises:

```python
from fastedgy.mcp import mcp_resource


@mcp_resource(
    "flow",
    uri_template="acme://flow/{workspace}/{reference}",
    description="One flow, with its messages.",
)
async def read_flow(uri: str) -> dict:
    workspace, reference = uri.removeprefix("acme://flow/").split("/")
    await enter_workspace(workspace)

    ...
```

A concrete URI is routed to the resource whose template prefix it matches, the longest first, so a template may sit
under another one's namespace.

## Registration rules

Registration is additive and never silent:

- a tool named after a built-in one is refused
- a duplicate name is refused
- a URI template that collides with `fastedgy://model/` or `fastedgy://models` is refused

There is no unregister: a tool an application does not want is a tool it does not register. The built-in ones are named
at wiring time instead.

## Removing built-in tools

```python
app.include_router(create_mcp_router(disabled_tools=["request", "delete_record"]))
```

A disabled tool leaves the catalogue **and** stops being callable, since a client may be working from a cached
`tools/list`. A name matching no built-in tool fails at wiring rather than passing for a working opt-out.

## Cache hints

Six methods carry a cache lifetime, and a tool call is not one of them. The defaults:

```python
DEFAULT_CACHE_HINTS = {
    "tools/list": CacheHint(ttl_ms=3_600_000, scope="public"),
    "resources/templates/list": CacheHint(ttl_ms=3_600_000, scope="public"),
    "resources/read": CacheHint(ttl_ms=300_000, scope="private"),
}
```

`public` means any caller may receive the cached response, which holds for the catalogue and the template list: they are
identical for everyone and static per deployment. A model's metadata is not, since a workspace extends it, so it stays
`private`. Override the whole mapping to suit a deployment:

```python
from mcp.server.caching import CacheHint

app.include_router(
    create_mcp_router(cache_hints={"tools/list": CacheHint(ttl_ms=60_000, scope="public")})
)
```

## Naming and instructions

The server reports the application title and a default instruction block telling an agent to read a model before
writing to it, and that writes apply immediately. Replace either:

```python
app.include_router(
    create_mcp_router(
        name="Acme",
        instructions="Tools over one Acme workspace. Call `get_model_info` before any write…",
    )
)
```

## Several endpoints

`create_mcp_router` builds an independent server each time, so one deployment can serve two audiences:

```python
app.include_router(create_mcp_router())
app.include_router(create_mcp_router(path="/mcp-readonly", disabled_tools=["create_record", "update_record", "delete_record", "request"]))
```

Both still authenticate the same way, and a key reaches whatever its owner reaches: an endpoint without the write tools
narrows what an agent is offered, not what the credential is allowed to do.

[Back to Overview](overview.md){ .md-button }
[Usage Guide](guide.md){ .md-button }
