# MCP Server - Usage guide

## Installation

The server ships behind an optional dependency:

```bash
pip install "fastedgy[mcp]"
```

Importing `fastedgy.mcp` without it raises a clear `ImportError` naming the extra.

## Enabling personal API keys

A JWT expires in minutes, which is no use to a machine client. The MCP server connects with a personal API key, and an
application only gets that way in when it asks for one:

```python
from fastedgy.app import FastEdgy

app = FastEdgy(user_api_tokens=True)
```

This registers a concrete `UserApiToken` model, unless the application declared its own by subclassing
`BaseUserApiToken`. Without it, no model, no table, and `create_mcp_router()` refuses to mount.

Generate the migration once the model is registered:

```bash
fastedgy db makemigrations -m "add user api tokens"
fastedgy db migrate
```

The key prefix is a setting, so keys stay recognisable per deployment:

```python
from fastedgy.config import BaseSettings


class AppSettings(BaseSettings):
    api_token_prefix: str = "acme_"
```

## Mounting the routes

Two routers: the MCP endpoint, which authenticates itself and belongs at the root, and the key management routes, which
sit with the rest of the API.

```python
from fastapi import APIRouter, Depends

from fastedgy.api.user_api_tokens import create_user_api_tokens_router
from fastedgy.depends.security import get_current_user
from fastedgy.mcp import create_mcp_router

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
router.include_router(create_user_api_tokens_router())

app.include_router(router)
app.include_router(create_mcp_router())
```

The MCP endpoint answers on `/mcp`. Pass `path="/agent"` to move it.

## Managing keys

| Method | Path | What it does |
|--------|------|--------------|
| `GET` | `/api/user-api-tokens` | The caller's keys, paginated, ordered and filtered like any model |
| `POST` | `/api/user-api-tokens` | Create a key and return the secret, once |
| `DELETE` | `/api/user-api-tokens/{id}` | Revoke a key |

```bash
curl -X POST https://app.example.com/api/user-api-tokens \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Claude"}'
```

```json
{
  "id": 1,
  "name": "Claude",
  "token_hint": "acme_A1b2C3d4",
  "token": "acme_A1b2C3d4e5F6...",
  "created_at": "2026-09-02T09:00:00Z",
  "expires_at": null,
  "last_used_at": null
}
```

Only the SHA-256 of the secret is stored. The `token` field appears in this response and never again: the listing
carries the hint alone. Pass `expires_at` to make a key die on its own.

A key authenticates every route of the API, not just the MCP endpoint, with the rights of its owner. It travels either
way:

```bash
curl https://app.example.com/api/products -H "Authorization: Bearer acme_A1b2..."
curl https://app.example.com/api/products -H "X-Api-Token: acme_A1b2..."
```

`X-Api-Token` matters for a host that keeps `Authorization` for its own OAuth token and lets you add one extra header.

## Connecting a client

**Claude Code**, and any client taking a header:

```bash
claude mcp add --transport http acme https://app.example.com/mcp \
  --header "Authorization: Bearer acme_A1b2..."
```

**A JSON configuration**:

```json
{
  "mcpServers": {
    "acme": {
      "type": "http",
      "url": "https://app.example.com/mcp",
      "headers": {"Authorization": "Bearer acme_A1b2..."}
    }
  }
}
```

**Claude app**: add a custom connector with the endpoint URL, set authentication to none, and add an `X-Api-Token`
header carrying the key.

## Working with the tools

An agent reads the catalogue first, then a model, then the records:

```json
{"name": "list_models", "arguments": {"workspace": "acme"}}
{"name": "get_model_info", "arguments": {"model": "product", "workspace": "acme"}}
{"name": "list_records", "arguments": {"model": "product", "workspace": "acme", "limit": 20}}
```

The `workspace` slug is required on the record tools of a multi-tenant application, and optional on the two catalogue
tools: a workspace can only add fields to a model, so its metadata is worth having before one is picked. An application
without workspaces never sees the argument at all.

### Filters

A rule is `[field, operator, value]`, or `[field, operator]` for an operator that takes none. A group is `["&", [...]]`
for all or `["|", [...]]` for any, and groups nest. `"and"` and `"or"` are accepted for the same thing.

```json
["name", "ilike", "%draft%"]
["&", [["state", "in", ["todo", "doing"]], ["assignee.email", "=", "a@b.co"]]]
["|", [["due_at", "is empty"], ["due_at", "<", "2026-01-01"]]]
```

A relation is a dotted path, and a foreign key compares on the id. The operators a field accepts are its
`filter_operators` in `get_model_info`, which also carries the grammar as `filter_syntax`. A rejected filter comes back
with that grammar attached.

### The escape hatch

`request` calls any endpoint of the API with the caller's rights, for what the model tools do not cover:

```json
{"name": "request", "arguments": {"method": "GET", "path": "/api/global/dataset/metadatas"}}
```

The path is absolute. A JSON response comes back as text; anything else comes back as a file, capped at 4 MB.

## Resources

A tool result can never carry a cache lifetime, a resource read can. The same content is readable both ways:

| URI | Content |
|-----|---------|
| `fastedgy://models/{workspace}` | The model catalogue |
| `fastedgy://model/{workspace}/{model}` | One model's metadata |

The workspace segment only exists in a multi-tenant application, and is optional there: leaving it out reads what every
workspace shares, and is its own cache entry.

[Back to Overview](overview.md){ .md-button }
[Advanced Usage](advanced.md){ .md-button .md-button--primary }
