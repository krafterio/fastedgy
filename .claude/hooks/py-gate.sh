#!/usr/bin/env bash
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$root" 2>/dev/null || exit 0
[ -f pyproject.toml ] || exit 0

out=$(uv run ruff check 2>&1)
if [ $? -ne 0 ]; then
  {
    echo "ruff check signale des problèmes — corrige-les avant de t'arrêter :"
    echo "$out"
  } >&2
  exit 2
fi
exit 0
