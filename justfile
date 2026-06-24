# Format Python code
format:
    uv run ruff format

# Lint Python code
lint:
    uv run ruff check

# Fix Python lint issues
fix:
    uv run ruff check --fix

# Type-check Python code
check:
    uv run pyright

# Run Python tests
test:
    uv run pytest

# Regenerate the golden OpenAPI snapshot
gen-openapi:
    uv run python -m tests.api.gen_openapi
