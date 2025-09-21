FastEdgy
--------

The base that makes web application development simple and fast with FastAPI and Edgy ORM.

## Features

- **API Routes Generator:** Automatically create CRUD management and export routes for models
- **Advanced Query Builder for API filter:** Create complex filters with nested rules and condition groupings validated by exposed metadata
- **Fields selector in API Response:** Define the list of fields that the JSON API should return with the ability to define fields on nested relationships compatible with single and multiple relationships
- **Metadata Generator:** Automatically create metadata info for models and fields
- **Container Service:** Centralizes and manages application-level lifecycle service classes with lazy loading
- **Queued Task:** Manage asynchronous tasks and background jobs with failover management and multi-workers
- **CLI:** Use Rich Click to improve command-line formatting and auto-register new commands
- **Edgy ORM Fields Extensions:** Add additional field types for Edgy and PostgreSQL
- **Email:** Use Jinja2 templates to generate and send emails
- **Storage:** Add storage management service
- **Alembic Extensions:** Add Alembic extensions to handle Edgy ORM/SQL Alchemy field migrations
- **Internationalization:** Use Babel to serve and extract translatable messages with CLI commands
- **Authentication:** Adds basic API endpoints for authentication management

## Documentation

Documentation is available at [fastedgy.krafter.io](https://krafterio.github.io/fastedgy).

## Prerequisites

- Python 3.13+
- UV (Python Package Manager recommended, see the [installation doc](https://docs.astral.sh/uv/getting-started/installation))
- PostgreSQL 15.0+

## Installation

```
uv add git+ssh://git@github.com/krafterio/fastedgy.git
```
Or
```
pip install git+ssh://git@github.com/krafterio/fastedgy.git
```

## Development

### Documentation Development

The project documentation is built using [MkDocs Material](https://squidfunk.github.io/mkdocs-material) with versioning
support via [Mike](https://github.com/jimporter/mike).

#### Local Development

To work on the documentation locally:

```bash
uv sync --dev
uv run mkdocs serve
```

The documentation will be available at `http://localhost:8000/fastedgy`.

#### Documentation Versioning

The documentation uses **mike** for version management:

- **Development version**: Push to `main` branch automatically deploys to `dev` version
- **Stable releases**: Create a tag (e.g., `0.1.0`) to automatically deploy version `0.1` as `latest`

**Useful commands:**

```bash
# List all deployed versions
uv run mike list

# Serve documentation locally with version selector (for testing) available at `http://localhost:8000`
uv run mike serve

# Manual deployment commands (for exceptional cases only)
# The --push flag automatically publishes to GitHub Pages
uv run mike deploy --push dev latest --update-aliases
uv run mike set-default --push latest
```

**Note:** In normal development, GitHub Actions handles deployment automatically when you push to `main` or create tags.

#### Publishing New Versions

1. **For development updates**: Simply push to `main` branch
   ```bash
   git push origin main
   ```

2. **For new releases**: Create and push a version tag
   ```bash
   git tag 0.2.0
   git push origin 0.2.0
   ```

The GitHub Action will automatically handle the documentation deployment.

## Commit message format convention

This project uses the **[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0)** naming convention.

### Basic structure of a Conventional commit

```
<type>(<scope>): <description>
```

- **type**: the type of modification made (required)
- **scope**: the scope (optional, but recommended)
- **description**: a short explanation (imperative, no capital letters, no period)

### Conventional Commits Types used

| Type     | Description                                                                    |
|----------|--------------------------------------------------------------------------------|
| feat     | New feature                                                                    |
| fix      | Bug fix                                                                        |
| docs     | Change in documentation                                                        |
| style    | Change of format (indentation, spaces, etc.) without functional impact         |
| refactor | Refactoring the code without adding or correcting functionality                |
| revert   | Reverting a previous commit                                                    |
| merge    | Merging branches                                                               |
| test     | Adding or modifying tests                                                      |
| chore    | Miscellaneous tasks without direct impact (build, dependencies, configs, etc.) |
| perf     | Performance improvement                                                        |
| ci       | Changes to CI/CD files (Github Actions, Gitlab CI, etc.)                       |
| release  | Creating a new release                                                         |

### Conventional Commits Scopes used

| Scope   | Description                                             |
|---------|---------------------------------------------------------|
| core    | Core backend logic and main platform features           |
| cli     | CLI commands and related functionality                  |
| orm     | ORM models, migrations, and related logic               |
| auth    | Authentication and authorization mechanisms             |
| api     | REST API endpoints, routes, and controllers             |
| config  | Global configuration and environment settings           |
| project | Project structure, global files, and overall management |

Contributing
------------

FastEdgy is an Open Source, community-driven project.

Issues and feature requests are tracked in the [Github issue tracker][3].

Pull Requests are tracked in the [Github pull request tracker][4].

License
-------

FastEdgy is released under the [MIT License][1].

About
-----

FastEdgy was originally created by [Krafter][2].

[1]: LICENSE
[2]: https://krafter.io
[3]: https://github.com/krafterio/fastedgy/issues
[4]: https://github.com/krafterio/fastedgy/pulls
