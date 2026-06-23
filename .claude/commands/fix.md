---
description: Auto-fix Python — ruff check --fix + ruff format
allowed-tools: Bash(uv run ruff check:*), Bash(uv run ruff format:*)
---
Auto-fix the Python backend:

1. `uv run ruff check --fix` — apply lint auto-fixes.
2. `uv run ruff format` — format the code.
3. `uv run ruff check` — report anything left, and fix it manually.

End with a short summary of what was auto-fixed vs. fixed by hand.
