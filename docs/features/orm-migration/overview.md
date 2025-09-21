# Database Migration - Overview

FastEdgy extends [Alembic](https://alembic.sqlalchemy.org/) with additional features to simplify database migrations for FastEdgy applications.

## What FastEdgy adds to Alembic

FastEdgy enhances Alembic with specialized support for FastEdgy-specific features:

- **Custom templates**: Pre-configured migration templates optimized for FastEdgy applications
- **Enum support**: Automatic handling of PostgreSQL enum types with specialized operations
- **Vector fields**: Automatic PostgreSQL vector extension management for AI/ML applications
- **Database views**: Support for database view creation and management in migrations
- **Multi-database**: Enhanced support for multiple database configurations
- **Nullable fields**: Intelligent handling of field nullability during migrations

## Key benefits

- **Zero configuration**: Works out of the box with FastEdgy applications
- **Automatic extensions**: PostgreSQL extensions are managed automatically when needed
- **Type safety**: Enhanced type checking for FastEdgy-specific field types
- **Multi-tenant ready**: Supports multi-database and multi-schema configurations
- **Developer friendly**: Clear error messages and helpful migration templates

## Integration with FastEdgy CLI

Database migrations are managed through the FastEdgy CLI with enhanced commands:

- Migration repository initialization with FastEdgy templates
- Automatic model discovery and schema generation
- Enhanced migration file generation with FastEdgy-specific imports
- Support for workspace-based multi-tenancy migration patterns

[Usage Guide](guide.md){ .md-button .md-button--primary }
