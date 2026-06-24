# FastEdgy Development Rules

## Stack & tooling

- Python 3.13+ · FastAPI + Edgy ORM · Pydantic · PostgreSQL 17+.
- Use `uv` for everything: `uv run <cmd>`, `uv add --dev <pkg>`.

## Commands (justfile)

- `just test` — run pytest
- `just check` — pyright
- `just lint` / `just fix` — ruff check (+ `--fix`)
- `just format` — ruff format
- `just gen-openapi` — regenerate the golden OpenAPI snapshot

## Automation

- Python files are auto-formatted with ruff on every Write/Edit (`PostToolUse` hook), so you rarely need `just format` by hand.
- A `Stop` hook runs `uv run ruff check` over the repo and blocks finishing when it fails — keep ruff check green.
- `/fix` runs `ruff check --fix` + `ruff format` and reports what is left.

## Code conventions

- Ruff line-length 120.
- No comments in code — keep only the `# Copyright … / # MIT License …` header; no boilerplate docstrings.
- Type hints everywhere.
- Service/business classes carry no `Service` suffix (e.g. `Bus`, `Storage`, `Mail`, `I18n`).
- Follow each file's existing language — don't inject French into English files or vice-versa.
- For framework concepts, consult the `fastedgy-docs` MCP (searchMkDoc/fetchMkDoc) before coding.

## Tests

- `tests/api/snapshots/openapi.json` is a golden snapshot asserted byte-for-byte by `tests/api/test_openapi_snapshot.py`; it guards consumer projects' OpenAPI against route/schema/typing drift. Keep `just test` green. When the spec changes on purpose, regenerate it with `just gen-openapi` and review the diff — never edit it to make the test pass.
- Integration tests need a reachable PostgreSQL (user able to CREATE DATABASE/EXTENSION): the schema is built via Alembic migrations into a `<db>-test-tpl` template DB, cloned per pytest-xdist worker, with `TRUNCATE` per test. They skip when Postgres is unavailable; the snapshot test needs no DB. Test models live in `fastedgy/test/models/` (one model per file); the test suite mirrors the package layout (e.g. `tests/api_route_model/`, `tests/api/`).
