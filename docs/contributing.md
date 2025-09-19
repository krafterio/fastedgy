---
hide:
  - navigation
---

# Contributing to FastEdgy

FastEdgy is an Open Source, community-driven project. We welcome contributions from everyone!

## Getting Started

Issues and feature requests are tracked in the [Github issue tracker](https://github.com/krafterio/fastedgy/issues).

Pull Requests are tracked in the [Github pull request tracker](https://github.com/krafterio/fastedgy/pulls).

## Development Setup

1. Fork the repository
2. Clone your fork locally
3. Install dependencies with `uv sync`
4. Create a feature branch
5. Make your changes
6. Run tests and linting
7. Submit a pull request

## Commit Message Conventions

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

## Code Style

- Follow PEP 8 guidelines
- Use type hints for all function parameters and return values
- Write docstrings for all public functions and classes
- Keep functions small and focused
- Write meaningful variable and function names

## Testing

- Write tests for all new features
- Ensure existing tests continue to pass
- Aim for high test coverage
- Use pytest for testing framework

## Documentation

- Update documentation for any new features
- Include code examples in docstrings
- Keep README.md up to date
- Use clear, concise language

## Pull Request Guidelines

1. **Create descriptive PR titles** following conventional commit format
2. **Provide detailed descriptions** of changes made
3. **Reference related issues** using `#issue_number`
4. **Ensure tests pass** before submitting
5. **Update documentation** as needed
6. **Keep PRs focused** - one feature or fix per PR

## Questions?

Feel free to open an issue for any questions about contributing to FastEdgy!
