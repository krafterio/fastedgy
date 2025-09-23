# JavaScript Rules

**AI rules for JavaScript/TypeScript frontend development with FastEdgy**

This file contains JavaScript and TypeScript rules for AI coding assistants when building frontends that consume FastEdgy APIs.

## Prerequisites

**MCP Server Required**: These rules work with the MCP server "fastedgy-docs" that provides access to FastEdgy documentation. Make sure you have configured the [MCP integration](../mcp.md) before using these rules.

## Rule File

Copy this content to your AI assistant configuration:

```markdown title="javascript.mdc"
---
description: Standardize FastEdgy API access through the project's fetcher (errors, pagination, caching, tests)
globs:
  - "app/src/**/*.js"
alwaysApply: true
---

# JavaScript rules (Fastedgy API client via fetcher)

## Project Facts
- A shared **fetcher** module (from `vue-fastedgy`) wraps the Fetch API
- Base URL is configured via env (e.g., `import.meta.env.VITE_API_BASE_URL`) or fetcher init
- Auth: Bearer token provided by the auth store/injector read by the fetcher
- Responses: JSON; pagination may be limit/offset or cursor-based
- Canonical API shapes/semantics are in FastEdgy docs (via MCP server "fastedgy-docs")
- **vue-fastedgy documentation** (fetcher, bus, etc.) is available in FastEdgy docs section "Vue.js" (accessible via MCP)

## OpenAPI-driven service design
1) BEFORE creating or editing any `src/api/*.js` service, MUST read the OpenAPI spec (from development server at /openapi.json) and locate the target operation.
2) The service function name SHOULD reference the `operationId` (or include it in a JSDoc tag), e.g.:
   /**
    * operationId: orders_list
    * GET /api/orders
    */
3) Parameters:
   - Path params: enforce presence and shape as per spec.
   - Query params: build with a `toQuery()` helper and only allow fields listed in the spec.
   - Body: build a minimal payload that matches the documented schema (drop unknowns).

## Error & response handling (spec alignment)
1) Map responses by status code as documented; handle documented error shapes first.
2) If the API returns an undocumented shape/status:
   - Treat as exceptional; surface a friendly message and log a TODO with the observed delta.
3) For critical endpoints, prefer adding a lightweight runtime guard (optional) to assert top-level fields documented by the spec.

## PR requirements (checklist)
- [ ] Link to OpenAPI spec used and `info.version` (or last-modified).
- [ ] Paste `operationId` and method+path.
- [ ] Note any deviations (temporary workarounds) with a TODO and owner.

## Rules
1) Single client
   1. All HTTP calls go through the **fetcher** (no raw `fetch()` and no third-party clients)
   2. The fetcher MUST handle:
      - Base URL joining + default headers (`Accept: application/json`)
      - Token injection (`Authorization: Bearer <token>`) when present
      - JSON auto-parse when `Content-Type` is JSON; handle 204 No Content
      - Abort/timeout using `AbortController` (default ~15s)
      - Consistent error mapping (see #3)

2) Domain services
   1. Place one service file per domain: `src/api/users.js`, `src/api/orders.js`, …
   2. Service functions call **fetcher** and return plain JS objects (never raw `Response`)
   3. Use small helpers:
      - `toQuery(params)` → builds query strings, drops empty/undefined
      - `pick(fields, obj)` if you need to shape payloads safely
   4. Example signatures (JS + JSDoc):
      ```js
      /** @typedef {{ items: any[], total: number, next?: string|null, prev?: string|null }} Page */

      /**
       * @param {{ q?: string, limit?: number, offset?: number }} params
       * @returns {Promise<Page>}
       */
      export async function listOrders(params) { /* use fetcher */ }

      /** @param {string} id @returns {Promise<any>} */
      export async function getOrder(id) { /* ... */ }

      /** @param {Record<string, any>} payload @returns {Promise<any>} */
      export async function createOrder(payload) { /* ... */ }

      /** @param {string} id @param {Record<string, any>} patch @returns {Promise<any>} */
      export async function updateOrder(id, patch) { /* ... */ }

      /** @param {string} id @returns {Promise<void>} */
      export async function deleteOrder(id) { /* ... */ }
      ```

3) Errors & resilience
   1. The fetcher maps errors to:
      ```js
      /** @typedef {{ code: string, status: number, message: string, details?: any }} ApiError */
      ```
   2. Treat 4xx as non-retryable; 5xx and network errors may retry with exponential backoff (max 2)
   3. If refresh tokens are supported, implement refresh **inside the fetcher** (single-flight lock), not in services
   4. Do not surface server stack traces; expose `code` + user-friendly `message`

4) Pagination / sorting / filtering
   1. Prefer cursor pagination (`cursor`, `page_size`) if the API supports it; otherwise `limit/offset` with `limit=25` default
   2. `list*` services should return `{ items, total, next?, prev? }` (or the canonical documented shape)
   3. In the UI, always show a clear Empty State; display `total` if provided by the API

5) Caching & revalidation
   1. Composables (`useX`) may provide an in-memory cache keyed by URL+params and a `refresh()` method to revalidate
   2. After create/update/delete, invalidate only affected cache keys (don’t nuke everything)
   3. Do not persist cache beyond the session by default

6) Security & compliance
   1. Never log tokens or sensitive data
   2. Sanitize/allowlist user-provided filters before sending to the API
   3. MUST consult MCP (`search` → `read`) to confirm exact payload shapes, status codes, and error envelopes **before** adding/changing a service
   4. When working with FastEdgy concepts (API Routes Generator, Query Builder, Fields Selector, Metadata Generator, Queued Tasks, i18n, Multi Tenant, Email, Storage, Authentication, settings) or vue-fastedgy features (fetcher config, bus, composables), MUST consult MCP **fastedgy-docs** → `search("keywords")` or `search("Vue.js [concept]")` for official patterns

7) Developer experience
   1. Use **JSDoc** to document function params/returns and shared shapes in `src/api/types.js` (or alongside each service)
   2. For critical endpoints, you may validate responses with a lightweight runtime check (e.g., custom guards) where appropriate
   3. Keep service modules side-effect free (pure functions calling fetcher)

8) Tests (services & fetcher)
   1. Use `vitest` + `msw` to mock HTTP at the network boundary
   2. Test **fetcher** once (token injection, timeout/abort, error mapping, retry policy)
   3. Each domain service includes happy-path and common failures (401, 404, 409, 429)
```

## What This Covers

- **API Integration**: Patterns for consuming FastEdgy APIs
- **Authentication**: JWT handling and auth flows
- **Error Handling**: API error responses and validation
- **TypeScript**: Type definitions for FastEdgy responses
- **HTTP Clients**: Fetch patterns and request configuration
- **State Management**: Patterns for managing API state
- **Form Handling**: Validation and submission patterns

## Usage with Different AI Tools

### Cursor
Create a `.cursor/rules/javascript.mdc` file or add to your main configuration.

### GitHub Copilot
Include in your JavaScript/TypeScript workspace settings.

### Other AI Tools
Adapt the format for your specific AI assistant.

## JavaScript Patterns Covered

These rules help the AI understand:

- FastEdgy API response structures
- Authentication token management
- Error handling with validation messages
- Async/await patterns for API calls
- TypeScript interfaces for API data

## Framework Compatibility

These rules work with:

- Vanilla JavaScript/TypeScript
- Vue.js applications (complement with vue.mdc)

## Customization Options

- Add framework-specific patterns
- Include your preferred HTTP client
- Modify error handling approaches
- Add custom TypeScript types

[Back to AI Rules Overview](overview.md)
