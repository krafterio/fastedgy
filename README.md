FastEdgy
--------

The base that makes web application development simple and fast with FastAPI and Edgy ORM.

## Prerequisites

- Python 3.13+
- UV (Python Package Manager recommended, see the [installation doc](https://docs.astral.sh/uv/getting-started/installation))

## Installation

```
pip install git+ssh://git@github.com/krafterio/fastedgy.git
```

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

License
-------

FastEdgy is released under the [MIT License][1].

About
-----

KastEdgy was originally created by [Krafter][2].

[1]: LICENSE
[2]: https://krafter.io
