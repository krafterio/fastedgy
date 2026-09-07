# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The tool catalogue of the MCP server.

Every model tool delegates to the very action the generated REST route calls,
so filters, field selection, view transformers and access guards behave the
same whether a record is read by the web app or by an agent.
"""

import base64
import json
from typing import Any, cast

import httpx
from fastapi import HTTPException

from fastedgy import context
from fastedgy.api_route_model.actions.create_action import create_item_action
from fastedgy.api_route_model.actions.delete_action import delete_item_action
from fastedgy.api_route_model.actions.get_action import get_item_action
from fastedgy.api_route_model.actions.list_action import list_items_action
from fastedgy.api_route_model.actions.patch_action import patch_item_action
from fastedgy.api_route_model.types import ModelCreate, ModelUpdate
from fastedgy.dependencies import get_service
from fastedgy.depends.security import find_workspace_user_model
from fastedgy.http import Request
from fastedgy.mcp.registry import McpRegistry, McpTool
from fastedgy.metadata_model import MetadataModelRegistry
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.orm.extra_fields import load_workspace_extra_fields
from fastedgy.orm.filter import And, R

# A response body the model cannot be handed as text comes back as a base64
# blob, which inflates by a third and lands in the context: past this, the
# agent is told to narrow the request rather than fed a truncated file.
MAX_BINARY_BYTES = 4 * 1024 * 1024

_MODEL_ARG = {"type": "string", "description": "Model name or its API plural, as returned by `list_models`."}
_FIELDS_ARG = {
    "type": "string",
    "description": "Comma-separated field selector, relations dotted (e.g. `name,company.name`). Omit for the default set.",
}
_WORKSPACE_ARG = {
    "type": "string",
    "description": "Slug of the workspace to read or write in, as returned by `list_workspaces`.",
}
_OPTIONAL_WORKSPACE_ARG = {
    "type": "string",
    "description": (
        "Optional slug of a workspace, as returned by `list_workspaces`. Pass it to see the fields "
        "that workspace adds; without it the answer covers what every workspace shares."
    ),
}

# The one thing `get_model_info` cannot say per field: the shape of the whole
# expression. It travels with the tool schema, with the model info and with a
# rejection, because an agent that guesses it gets a 422 with nothing to fix.
FILTER_SYNTAX = {
    "rule": ["<field>", "<operator>", "<value>"],
    "rule_without_value": ["<field>", "<operator>"],
    "group": ["& (all) | (any)", ["<rule or group>", "..."]],
    "notes": [
        'A group joins with "&" or "|" ("and" and "or" are accepted too).',
        "A relation is a dotted path: `assignee.email`.",
        'A foreign key compares on the id: ["assignee", "=", 12].',
        "The operators a field accepts are its `filter_operators` in `get_model_info`.",
        "Groups nest: a group is a valid member of another group.",
    ],
    "examples": [
        ["name", "ilike", "%draft%"],
        ["&", [["state", "in", ["todo", "doing"]], ["assignee.email", "=", "a@b.co"]]],
        ["|", [["due_at", "is empty"], ["due_at", "<", "2026-01-01"]]],
    ],
}

_FILTER_ARG = {
    "type": "array",
    "description": (
        "Filter expression. A rule is [field, operator] or [field, operator, value]; a group is "
        '["&", [...]] for all or ["|", [...]] for any, and groups nest. A relation is a dotted path '
        "and a foreign key compares on the id. Each field's operators are its `filter_operators` in "
        '`get_model_info`. Examples: ["name", "ilike", "%draft%"] and '
        '["&", [["state", "in", ["todo", "doing"]], ["assignee.email", "=", "a@b.co"]]]'
    ),
}

_CONDITION_ALIASES = {"and": "&", "or": "|"}


def _normalize_filter(node: Any) -> Any:
    """A group joins with "&" or "|", which no agent writes spontaneously: the
    English spelling is taken for what it obviously means."""
    if not isinstance(node, list) or len(node) != 2 or not isinstance(node[0], str) or not isinstance(node[1], list):
        return node

    condition = _CONDITION_ALIASES.get(node[0].strip().lower(), node[0])

    return [condition, [_normalize_filter(rule) for rule in node[1]]]


def _model_tools(workspaced: bool) -> list[dict[str, Any]]:
    def properties(*, model: bool = True, **extra: Any) -> dict[str, Any]:
        props: dict[str, Any] = {**({"model": _MODEL_ARG} if model else {}), **extra}

        if workspaced:
            props["workspace"] = _WORKSPACE_ARG

        return props

    def required(*names: str) -> list[str]:
        return [*names, *(["workspace"] if workspaced else [])]

    return [
        {
            "name": "list_models",
            "description": (
                "The models this API exposes: name, API plural and label. The entry point before anything "
                "else. The same content is readable as the resource it names, which a client may cache."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"workspace": _OPTIONAL_WORKSPACE_ARG} if workspaced else {},
            },
        },
        {
            "name": "get_model_info",
            "description": (
                "Fields of one model with their type, flags, target relation and filter operators. "
                "Call it before the first read or write on a model and never guess a field name or an "
                "operator. The same content is readable as the resource it names, which a client may cache."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "model": _MODEL_ARG,
                    **({"workspace": _OPTIONAL_WORKSPACE_ARG} if workspaced else {}),
                },
                "required": ["model"],
            },
        },
        {
            "name": "list_records",
            "description": "A page of records. The only source on what exists: never describe a record you have not read.",
            "input_schema": {
                "type": "object",
                "properties": properties(
                    filter=_FILTER_ARG,
                    fields=_FIELDS_ARG,
                    order_by={"type": "string", "description": "e.g. `created_at:desc,name:asc`."},
                    limit={"type": "integer", "default": 50},
                    offset={"type": "integer", "default": 0},
                ),
                "required": required("model"),
            },
        },
        {
            "name": "get_record",
            "description": "One record by id.",
            "input_schema": {
                "type": "object",
                "properties": properties(id={"type": "integer"}, fields=_FIELDS_ARG),
                "required": required("model", "id"),
            },
        },
        {
            "name": "create_record",
            "description": "Create a record. Applies immediately: only write what the user actually asked for.",
            "input_schema": {
                "type": "object",
                "properties": properties(
                    values={"type": "object", "description": "Field values. A foreign key takes the id."},
                    fields=_FIELDS_ARG,
                ),
                "required": required("model", "values"),
            },
        },
        {
            "name": "update_record",
            "description": "Update a record. Applies immediately: pass only the fields that change.",
            "input_schema": {
                "type": "object",
                "properties": properties(
                    id={"type": "integer"},
                    values={"type": "object", "description": "Only the fields that change."},
                    fields=_FIELDS_ARG,
                ),
                "required": required("model", "id", "values"),
            },
        },
        {
            "name": "delete_record",
            "description": "Delete a record. Applies immediately and cannot be undone.",
            "input_schema": {
                "type": "object",
                "properties": properties(id={"type": "integer"}),
                "required": required("model", "id"),
            },
        },
        {
            "name": "request",
            "description": (
                "Call any endpoint of this API with the caller's own rights, for what the model tools do not cover. "
                "The path is absolute (e.g. `/api/global/dataset/metadatas`). A non-JSON response comes back as a file."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "path": {"type": "string", "description": "Absolute path, starting with `/`."},
                    "body": {"type": "object", "description": "JSON body, for the methods that take one."},
                    "query": {"type": "object", "description": "Query string parameters."},
                    "headers": {"type": "object", "description": "Extra headers (e.g. `X-Fields`, `X-Filter`)."},
                },
                "required": ["method", "path"],
            },
        },
    ]


async def get_tools() -> list[dict[str, Any]]:
    workspaced = find_workspace_user_model() is not None
    tools = _model_tools(workspaced)

    if workspaced:
        tools.insert(
            0,
            {
                "name": "list_workspaces",
                "description": "The workspaces the caller belongs to. Every other tool takes one of these slugs.",
                "input_schema": {"type": "object", "properties": {}},
            },
        )

    return tools + [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in get_service(McpRegistry).get_tools()
    ]


async def enter_workspace(slug: str | None, required: bool = True) -> None:
    """Run the rest of the call as the given workspace, refusing a slug the
    caller is not a member of.

    The catalogue reads do not require one: a workspace can only add fields to
    a model, so its metadata is worth having even before one is picked.
    """
    model = find_workspace_user_model()

    if model is None:
        return

    if not slug:
        if not required:
            return

        raise HTTPException(status_code=400, detail="A `workspace` slug is required")

    user = context.get_user()
    workspace_user = (
        await model.query.select_related("workspace")
        .filter(And(R("user", "=", getattr(user, "id", None)), R("workspace.slug", "=", slug)))
        .first()
    )
    workspace = getattr(workspace_user, "workspace", None) if workspace_user else None

    if not workspace_user or not workspace:
        raise HTTPException(status_code=404, detail=f"No workspace '{slug}' for this user")

    context.set_workspace(workspace)
    context.set_workspace_user(workspace_user)
    await load_workspace_extra_fields()


async def _resolve_model(name: str) -> type[BaseModel | BaseView]:
    model_cls = await get_service(MetadataModelRegistry).get_model_from_name(name)

    if model_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown model '{name}'. Call `list_models` for the catalogue.")

    return model_cls


async def _list_workspaces() -> list[dict[str, Any]]:
    model = find_workspace_user_model()

    if model is None:
        return []

    user = context.get_user()
    memberships = await model.query.select_related("workspace").filter(R("user", "=", getattr(user, "id", None))).all()
    workspaces = [getattr(membership, "workspace", None) for membership in memberships]

    return [
        {"slug": workspace.slug, "name": getattr(workspace, "name", None)}
        for workspace in workspaces
        if workspace is not None
    ]


# The two catalogue reads, as resources rather than tools only: a tool result
# can never carry a TTL, a resource read can. The workspace is in the URI, so
# two workspaces are two cache entries.
MODEL_RESOURCE_SCHEME = "fastedgy://model/"
MODELS_RESOURCE_SCHEME = "fastedgy://models"
BUILTIN_RESOURCE_PREFIXES = (MODEL_RESOURCE_SCHEME, MODELS_RESOURCE_SCHEME)
BUILTIN_TOOL_NAMES = frozenset(
    {
        "list_workspaces",
        "list_models",
        "get_model_info",
        "list_records",
        "get_record",
        "create_record",
        "update_record",
        "delete_record",
        "request",
    }
)


def model_resource_uri(model: str, workspace: str | None = None) -> str:
    return f"{MODEL_RESOURCE_SCHEME}{workspace}/{model}" if workspace else f"{MODEL_RESOURCE_SCHEME}{model}"


def models_resource_uri(workspace: str | None = None) -> str:
    return f"{MODELS_RESOURCE_SCHEME}/{workspace}" if workspace else MODELS_RESOURCE_SCHEME


def _current_workspace_slug() -> str | None:
    return getattr(context.get_workspace(), "slug", None)


async def get_model_metadata(model: str) -> dict[str, Any]:
    """What a model is made of, plus the shape of a filter expression, which no
    per-field description can carry."""
    metadata = await get_service(MetadataModelRegistry).get_metadata(model)

    return {
        **metadata.model_dump(),
        "filter_syntax": FILTER_SYNTAX,
        "resource_uri": model_resource_uri(model, _current_workspace_slug()),
    }


async def _enter_resource_workspace(uri: str, scheme: str, tail: int) -> list[str]:
    """Consume the URI after `scheme`: an optional workspace slug, then `tail`
    segments of its own.

    The slug is what makes two workspaces two cache entries. Leaving it out is
    a read of what every workspace shares, and its own entry.
    """
    workspaced = find_workspace_user_model() is not None
    path = [segment for segment in uri[len(scheme) :].split("/") if segment]
    slugged = len(path) == tail + 1 and workspaced

    if len(path) != tail and not slugged:
        raise HTTPException(status_code=400, detail=f"Unexpected shape for '{uri}'")

    await enter_workspace(path[0] if slugged else None, required=False)

    return path[-tail:] if tail else []


async def read_resource(uri: str) -> dict[str, Any]:
    """`fastedgy://models/<workspace>` for the catalogue,
    `fastedgy://model/<workspace>/<name>` for one model, both without the
    workspace segment where the app has none."""
    if uri.startswith(MODEL_RESOURCE_SCHEME):
        (model,) = await _enter_resource_workspace(uri, MODEL_RESOURCE_SCHEME, tail=1)

        return await get_model_metadata(model)

    if uri.startswith(MODELS_RESOURCE_SCHEME):
        await _enter_resource_workspace(uri, MODELS_RESOURCE_SCHEME, tail=0)

        return {"models": await _list_models(), "resource_uri": models_resource_uri(_current_workspace_slug())}

    registered = get_service(McpRegistry).find_resource(uri)

    if registered is not None:
        return await registered.reader(uri)

    raise HTTPException(status_code=404, detail=f"Unknown resource '{uri}'")


async def _list_models() -> list[dict[str, Any]]:
    metadatas = await get_service(MetadataModelRegistry).get_map_models()

    return sorted(
        (
            {"name": metadata.name, "api_name": metadata.api_name, "label": metadata.label_plural}
            for metadata in metadatas.values()
        ),
        key=lambda entry: entry["name"],
    )


async def _request(
    request: Request,
    method: str,
    path: str,
    body: Any = None,
    query: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Dispatch on the app itself, credentials included: the endpoint runs
    through its own dependencies, so the caller reaches exactly what its rights
    allow and nothing is re-implemented here."""
    if path.rstrip("/") == request.url.path.rstrip("/"):
        raise HTTPException(status_code=400, detail="The MCP endpoint cannot call itself")

    app = request.scope.get("app")

    if app is None:
        raise HTTPException(status_code=500, detail="The MCP transport runs outside of an ASGI app")

    authorization = request.headers.get("authorization")
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.internal") as client:
        response = await client.request(
            method.upper(),
            path if path.startswith("/") else f"/{path}",
            json=body,
            params={key: value for key, value in (query or {}).items() if value is not None},
            headers={
                "Accept": "application/json",
                **({"Authorization": authorization} if authorization else {}),
                **(headers or {}),
            },
            timeout=120.0,
        )

    return response


def _response_content(response: httpx.Response) -> list[Any]:
    from mcp import types

    content_type = response.headers.get("content-type", "")
    payload = response.content

    if "json" in content_type or not payload:
        text = payload.decode(errors="replace") if payload else ""

        return [types.TextContent(type="text", text=f"HTTP {response.status_code}\n{text}")]

    if len(payload) > MAX_BINARY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Response of {len(payload)} bytes exceeds the {MAX_BINARY_BYTES} bytes an MCP call can carry",
        )

    return [
        types.EmbeddedResource(
            type="resource",
            resource=types.BlobResourceContents(
                uri=f"fastedgy://response{response.request.url.path}",
                mime_type=content_type.split(";")[0] or "application/octet-stream",
                blob=base64.b64encode(payload).decode(),
            ),
        )
    ]


async def call_tool(request: Request, name: str, arguments: dict[str, Any]) -> list[Any]:
    from mcp import types

    registered = get_service(McpRegistry).get_tool(name)

    if registered is not None:
        return await _call_registered_tool(registered, arguments)

    if name == "request":
        response = await _request(
            request,
            arguments["method"],
            arguments["path"],
            arguments.get("body"),
            arguments.get("query"),
            arguments.get("headers"),
        )

        return _response_content(response)

    if name == "list_workspaces":
        return _json_content(await _list_workspaces())

    # Everything below reads the model catalogue, which a workspace extends with
    # its own extra fields: enter it first, metadata included. The two catalogue
    # tools answer without one, the record tools do not.
    catalogue = name in ("list_models", "get_model_info")
    await enter_workspace(arguments.get("workspace"), required=not catalogue)

    if name == "list_models":
        return _json_content(
            {"models": await _list_models(), "resource_uri": models_resource_uri(_current_workspace_slug())}
        )

    if name == "get_model_info":
        return _json_content(await get_model_metadata(arguments["model"]))

    model_cls = await _resolve_model(arguments["model"])
    fields = arguments.get("fields")

    if name == "list_records":
        filters = arguments.get("filter")

        try:
            result = await list_items_action(
                request,
                model_cls,
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0),
                order_by=arguments.get("order_by"),
                fields=fields,
                # The wire format is the JSON of the X-Filter header, so what the
                # agent builds goes through the parser the web app already uses.
                filters=json.dumps(_normalize_filter(filters)) if filters else None,
            )
        except HTTPException as e:
            raise _filter_error(e, filters) from e

        return _json_content(result.model_dump())

    if name == "get_record":
        item = await get_item_action(request, model_cls, arguments["id"], fields=fields)

        return _json_content(_dump(item))

    if name == "create_record":
        data = cast(Any, ModelCreate[model_cls]).model_validate(arguments["values"])
        item = await create_item_action(request, model_cls, data, fields=fields)

        return _json_content(_dump(item))

    if name == "update_record":
        data = cast(Any, ModelUpdate[model_cls]).model_validate(arguments["values"])
        item = await patch_item_action(request, model_cls, arguments["id"], data, fields=fields)

        return _json_content(_dump(item))

    if name == "delete_record":
        await delete_item_action(request, model_cls, arguments["id"])

        return [types.TextContent(type="text", text="Deleted")]

    raise HTTPException(status_code=404, detail=f"Unknown tool '{name}'")


async def _call_registered_tool(tool: McpTool, arguments: dict[str, Any]) -> list[Any]:
    result = await tool.handler(arguments)

    # A handler may build its own content blocks; anything else is JSON.
    return result if isinstance(result, list) and result and hasattr(result[0], "type") else _json_content(result)


def _filter_error(error: HTTPException, filters: Any) -> HTTPException:
    """A rejected filter comes back with the grammar attached: the parser says
    what is wrong, never what the shape should have been."""
    if error.status_code != 422 or not filters:
        return error

    return HTTPException(
        status_code=422,
        detail=f"{error.detail}. Expected shape: {json.dumps(FILTER_SYNTAX, ensure_ascii=False)}",
    )


def _dump(item: Any) -> Any:
    return item if isinstance(item, dict) else item.model_dump()


def _json_content(value: Any) -> list[Any]:
    from mcp import types

    return [types.TextContent(type="text", text=json.dumps(value, ensure_ascii=False, default=str))]


__all__ = [
    "BUILTIN_RESOURCE_PREFIXES",
    "BUILTIN_TOOL_NAMES",
    "FILTER_SYNTAX",
    "MAX_BINARY_BYTES",
    "MODELS_RESOURCE_SCHEME",
    "MODEL_RESOURCE_SCHEME",
    "call_tool",
    "enter_workspace",
    "get_model_metadata",
    "get_tools",
    "model_resource_uri",
    "models_resource_uri",
    "read_resource",
]
