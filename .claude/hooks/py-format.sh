#!/usr/bin/env bash
# PostToolUse (Write|Edit|MultiEdit)
set -uo pipefail

input=$(cat)
file=$(printf '%s' "$input" \
  | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' \
  | head -1 \
  | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/')

[ -n "${file:-}" ] || exit 0
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$root" 2>/dev/null || exit 0
uv run ruff format "$file" >/dev/null 2>&1 || true
exit 0
