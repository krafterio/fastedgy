# Format Python code
format *args:
    uv run ruff format {{args}}

# Lint Python code
lint *args:
    uv run ruff check {{args}}

# Fix Python lint issues
fix *args:
    uv run ruff check --fix {{args}}

# Type-check Python code
check *args:
    uv run pyright {{args}}

# Fix, Format, Check and Lint Python code
fcl:
    uv run ruff check --fix
    uv run ruff format
    uv run pyright
    uv run ruff check

# Run Python tests
test *args:
    uv run pytest {{args}}

# Regenerate the golden OpenAPI snapshot
gen-openapi *args:
    uv run python -m tests.api.gen_openapi {{args}}
