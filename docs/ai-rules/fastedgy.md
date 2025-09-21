# FastEdgy Core Rules

**AI rules for FastEdgy framework patterns and conventions**

This file contains core rules for AI coding assistants to better understand FastEdgy patterns, architecture, and conventions.

## Prerequisites

**MCP Server Required**: These rules work with the MCP server "fastedgy-docs" that provides access to FastEdgy documentation. Make sure you have configured the [MCP integration](../mcp.md) before using these rules.

## Rule File: fastedgy.mdc

Copy this content to your AI assistant configuration:

```markdown title="fastedgy.mdc"
---
description: Make the Agent consult FastEdgy docs via MCP before generating or changing code that depends on framework semantics
globs:
  - "**/*.py"
  - "**/*.js"
  - "**/*.vue"
alwaysApply: true
---

# MCP usage rules for FastEdgy

## Project Facts
- The canonical product documentation is built with MkDocs and exposed via an MCP server registered in this workspace
- The Agent can use MCP tools: `search(query)`, `read(uri)` from server "fastedgy-docs"
- Documentation covers both **Python** (FastAPI/EdgyORM/FastEdgy backend) and **JavaScript/Vue** (vue-fastedgy frontend) aspects

## Sources of truth (priority order)
1) Local OpenAPI spec (running dev server): available at /openapi.json endpoint
2) FastEdgy product docs via MCP server "fastedgy-docs" (MkDocs)
3) Existing service code and tests in this repo

## Mandatory preflight for any API change
1. MUST fetch and read the OpenAPI spec from the development server before adding/changing a request
2. MUST locate the **operation** by `operationId` or by (method + path)
3. MUST verify: path params, query params, request body schema, expected status codes, and response schema
4. If a mismatch is found between spec and current code:
   - Prefer aligning to the spec; if backend is the source of truth, open a TODO with the spec delta
5. PRs MUST include:
   - `operationId` (or method+path), the spec `info.version` (or last-modified), and links to the MkDocs page consulted via MCP

## Fallbacks
- If the OpenAPI spec is not reachable:
  - **stop** and request the spec export before coding endpoints

## Rules
1. WHEN a question concerns FastEdgy concepts (ORM Edgy, DI, API Routes Generator, Query Builder, Fields Selector, Metadata Generator, ORM Extensions, Database Migration, Queued Tasks, CLI, i18n, Multi Tenant, Email, Storage, Authentication, settings) OR vue-fastedgy features (fetcher, bus, composables):
   - MUST first call MCP `search` with 3–6 keywords (use "Vue.js [concept]" for vue-fastedgy features)
   - THEN call MCP `read` on the top-1 relevant doc to confirm API/constraints before coding

2. MUST cite the doc section (file name or heading) you used to justify decisions in the code comment or PR message

3. DO NOT invent framework APIs. If missing in docs, propose a thin wrapper with clear TODO and link to the doc gap

4. When unsure between multiple patterns:
   - Prefer the documented examples from the MCP doc page over past code in the repo
```

## What This Covers

- **Container Service**: Dependency injection patterns and service registration
- **API Route Models**: Automatic CRUD generation and route patterns
- **Queued Tasks**: Background task patterns and queue management
- **Configuration**: Settings management and environment handling
- **Database**: ORM patterns with Edgy and migration conventions
- **CLI**: Click-based command patterns
- **Project Structure**: Recommended file organization

## Usage with Different AI Tools

### Cursor
Create a `.cursor/rules/fastedgy.mdc` file in your project root and paste the content above.

### GitHub Copilot
Add to your workspace settings or use as context documentation.

### Other AI Tools
Adapt the format as needed for your specific AI coding assistant.

## Customization

Feel free to modify these rules to match your project's specific requirements:

- Add project-specific patterns
- Modify naming conventions
- Include additional dependencies
- Adjust for your deployment environment

[Back to AI Rules Overview](../ai-rules.md)
