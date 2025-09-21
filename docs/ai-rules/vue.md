# Vue.js Rules

**AI rules for Vue.js development with vue-fastedgy**

This file contains Vue.js-specific rules for AI coding assistants when using vue-fastedgy to integrate with FastEdgy backends.

## Prerequisites

**MCP Server Required**: These rules work with the MCP server "fastedgy-docs" that provides access to FastEdgy documentation. Make sure you have configured the [MCP integration](../mcp.md) before using these rules.

## Rule File: vue.mdc

Copy this content to your AI assistant configuration:

```markdown title="vue.mdc"
---
description: Vue 3 (Composition API) frontend rules for components, stores, and UI integration with Fastedgy
globs:
  - "app/src/**/*.vue"
  - "app/src/**/*.js"
  - !node_modules/**
  - "!dist/**"
alwaysApply: true
---

# Vue 3 rules (Fastedgy frontend, JavaScript)

## Project Facts
- Stack: Vue 3 + Vite, Composition API only (no Options API).
- State: Pinia.
- Router: Vue Router (SPA).
- UI: prefer headless/lightweight libraries.
- HTTP: use the project's **fetcher** module from `vue-fastedgy` (not Axios).
- FastEdgy product docs are exposed via an MCP server named "fastedgy-docs".
- **vue-fastedgy documentation** (fetcher, bus, composables) is available in FastEdgy docs section "Vue.js".

## Rules
1) Components
   1. Use `<script setup>` in SFCs.
   2. Keep components focused (one UI responsibility). Use `defineProps` / `defineEmits`.
   3. Do NOT call the network in `.vue` files; put IO in composables (`src/composables/x.js`) or services (`src/api/x.js`) that use the **fetcher**.

2) Stores (Pinia)
   1. One store per domain (`useUserStore`, `useOrdersStore`, …).
   2. Stores do not call `fetch` directly—always go through **fetcher** via services in `src/api/`.
   3. Track `status` ('idle' | 'loading' | 'success' | 'error') and a serializable `error`.

3) Async data
   1. Prefer composables returning `{ data, status, error, refresh }`.
   2. Deterministic loading states (skeletons/placeholders); avoid infinite spinners.
   3. Use `Suspense` only for top-level views, not micro-interactions.

4) Accessibility & i18n
   1. Add ARIA where relevant; manage focus for modals/menus.
   2. All user-facing text goes through i18n—no hardcoded strings in logic.

5) Navigation & security
   1. Global guard: if route meta `auth.required === true`, validate token via the user store; redirect to `/login?next=…`.
   2. Never embed secrets; config comes from `import.meta.env`.

6) FastEdgy integration (MCP-first)
   1. If a task involves FastEdgy concepts (API Routes Generator, Query Builder, Fields Selector, Metadata Generator, Queued Tasks, i18n, Multi Tenant, Email, Storage, Authentication, settings) OR **vue-fastedgy features** (fetcher, bus, composables):
      - MUST first call MCP **fastedgy-docs** → `search("keywords")` or `search("Vue.js [concept]")` for vue-fastedgy, then `read(uri)` for the top result **before coding**.
      - In PRs, reference the consulted doc section (file/heading or link).
   2. If docs don't cover the need, create a minimal wrapper and add a TODO with a link to the doc gap.

7) UI tests
   1. Use `@testing-library/vue`.
   2. Mock **services** (which use fetcher), not Pinia stores, for unit tests.
   3. Every bug fix adds a narrow regression test.

8) Performance
   1. Code-split heavy views (`defineAsyncComponent`).
   2. Memoize expensive derived data with `computed`; avoid unnecessary watchers.
   3. Lists with > ~200 visible items must use pagination or virtualization.
```

## What This Covers

- **vue-fastedgy Integration**: Composables and store patterns
- **Fetcher Usage**: HTTP client patterns with Vue lifecycle
- **Auth Store**: Authentication state management
- **Bus System**: Event communication between components
- **Metadata Service**: Dynamic UI generation patterns
- **Router Integration**: Route protection and navigation
- **Error Handling**: Validation error formatting
- **Component Patterns**: Best practices for Vue components

## Usage with Different AI Tools

### Cursor
Create a `.cursor/rules/vue.mdc` file.

### GitHub Copilot
Include in your Vue.js workspace settings.

### Other AI Tools
Adapt the format for your specific AI assistant.

## Vue.js Patterns Covered

These rules help the AI understand:

- vue-fastedgy composables (`useFetcher`, `useAuthStore`, `useBus`)
- Automatic request cancellation patterns
- Authentication flow with Vue Router
- Event bus communication patterns

## Vue.js Specific Features

- **Composition API**: Proper composable usage
- **Lifecycle Integration**: Automatic cleanup patterns
- **Pinia Stores**: State management with vue-fastedgy
- **Router Guards**: Authentication-based route protection
- **Component Communication**: Bus-based event patterns

## Complementary Rules

For complete coverage, also use:

- [FastEdgy Core Rules](fastedgy.md) - Backend patterns
- [JavaScript Rules](javascript.md) - General frontend patterns

## Customization Ideas

- Add your preferred UI component library patterns
- Include project-specific composables
- Modify authentication flow for your needs
- Add custom validation patterns

[Back to AI Rules Overview](../ai-rules.md)
