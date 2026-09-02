# MCP Server

Expose the API to an AI assistant over the [Model Context Protocol](https://modelcontextprotocol.io), on a single
stateless HTTP endpoint. The models an application already exposes as REST routes become tools an agent can read and
write, with the rights of the key it connects with.

Every tool goes through the same action its generated REST route calls, so filters, field selection, access guards and
view transformers behave identically whether a record is read by a web app or by an agent.

!!! note

    This is the MCP server *your application* serves. For the one that serves the FastEdgy documentation to your AI
    assistant, see [MCP integration](../../mcp.md).

## Key features

- **Stateless transport**: the `2026-07-28` protocol, no handshake and no session, so any worker answers any call
- **Model tools**: list, read, create, update and delete on every model the API exposes
- **Filter grammar**: the shape of a filter expression travels with the tool schema, the model info and a rejection
- **Cacheable resources**: the model catalogue and a model's metadata, keyed by workspace
- **Personal API keys**: a durable credential a machine client connects with, standing in for a JWT everywhere
- **Extensible**: an application registers its own tools and resources, and names the built-in ones it does not expose

## Built-in tools

| Tool | What it does |
|------|--------------|
| `list_workspaces` | The workspaces the caller belongs to (multi-tenant applications only) |
| `list_models` | The models the API exposes: name, API plural and label |
| `get_model_info` | Fields of one model with their type, flags, target relation and filter operators |
| `list_records` | A page of records, filtered and ordered |
| `get_record` | One record by id |
| `create_record` | Create a record |
| `update_record` | Update a record |
| `delete_record` | Delete a record |
| `request` | Any endpoint of the API, for what the model tools do not cover |

## Use cases

- **Assistant over your data**: an agent that reads and updates records without a scripted integration
- **Server-side integration**: no local script to install and keep up to date, the deployment holds the logic
- **Domain tools**: a business operation exposed as one tool instead of a sequence of record writes

## Requirements

The server ships behind an optional dependency, and personal API keys are opt-in:

```bash
pip install "fastedgy[mcp]"
```

[Usage Guide](guide.md){ .md-button .md-button--primary }
[Advanced Usage](advanced.md){ .md-button }
