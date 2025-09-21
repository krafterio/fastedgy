# Python Rules

**AI rules for Python development with FastEdgy**

This file contains Python-specific rules for AI coding assistants when working with FastEdgy applications.

## Prerequisites

**MCP Server Required**: These rules work with the MCP server "fastedgy-docs" that provides access to FastEdgy documentation. Make sure you have configured the [MCP integration](../mcp.md) before using these rules.

## Rule File: python.mdc

Copy this content to your AI assistant configuration:

```markdown title="python.mdc"
---
description: Python backend conventions for FastAPI and Edgy ORM: structure, errors, and testing
globs:
  - "server/**/*.py"
alwaysApply: true
---

# Python / FastAPI / Edgy conventions

## Project Facts
- FastEdgy product docs are exposed via an MCP server named "fastedgy-docs"
- Documentation covers FastAPI patterns, EdgyORM usage, dependency injection, and FastEdgy framework features

## Rules
1. Python target: 3.13. Use type hints everywhere. pydantic v2 models
2. Services: Single-responsibility functions; dependency injection via FastAPI Depends; no global state
3. Edgy ORM: Use async session patterns; avoid N+1 by preloading relations; never perform writes in GET handlers
4. Errors: Raise HTTPException with detail enums; validate inputs with pydantic; log at error boundary
5. Tests: Pytest; async tests with anyio; one test module per feature; add regression test for every bugfix
6. Formatting: Ruff/Black defaults; docstrings Google style for public funcs/classes
7. FastEdgy integration (MCP-first):
   - When working with FastEdgy concepts (ORM Edgy, DI, API Routes Generator, Query Builder, Fields Selector, Metadata Generator, ORM Extensions, Database Migration, Queued Tasks, CLI, i18n, Multi Tenant, Email, Storage, Authentication, settings), MUST first call MCP **fastedgy-docs** → `search("keywords")`, then `read(uri)` for the top result **before coding**
   - In PRs, reference the consulted doc section (file/heading or link)
   - DO NOT invent framework APIs. If missing in docs, propose a thin wrapper with clear TODO and link to the doc gap
```

## What This Covers

- **Type Hints**: Proper typing for FastEdgy components
- **Async/Await**: Asynchronous patterns and best practices
- **Pydantic Models**: Schema definition and validation patterns
- **SQLAlchemy/Edgy**: ORM patterns and query building
- **FastAPI Integration**: Endpoint definition and dependency injection
- **Error Handling**: Exception patterns and error responses
- **Testing**: Test patterns for FastEdgy applications
- **Code Style**: Python conventions and formatting

## Usage with Different AI Tools

### Cursor
Create a `.cursor/rules/python.mdc` file.

### GitHub Copilot
Include in your Python workspace configuration.

### Other AI Tools
Adapt the format for your specific AI assistant.

## Python-Specific Patterns

These rules help the AI understand:

- FastEdgy's async-first approach
- Proper dependency injection patterns
- Type-safe model definitions
- Error handling conventions
- Testing best practices

## Customization Tips

- Adjust type hints based on your Python version
- Modify patterns for your testing framework preference
- Add project-specific imports and dependencies
- Include custom exception classes

[Back to AI Rules Overview](../ai-rules.md)
