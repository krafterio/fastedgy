# Metadata Generator

Automatically generates structured metadata for your Edgy ORM models, providing complete field information, validation rules, and relationship data for dynamic frontend applications.

## What it generates

The Metadata Generator analyzes your models and produces comprehensive metadata including:

- **Field information**: Name, type, label, validation rules
- **Data constraints**: Required, readonly, default values
- **Filter operators**: Available query operators per field type
- **Relationships**: Foreign keys and related model references
- **Labels**: Human-readable field and model names

## Key features

- **Automatic discovery**: Scans model fields and relationships
- **Type mapping**: Converts ORM field types to metadata types
- **Label generation**: Creates readable labels from field names
- **Registry system**: Control which models expose metadata
- **API integration**: Serves metadata via `/api/dataset/metadatas` endpoints
- **Frontend ready**: Structured for dynamic form/UI generation

## Use cases

- **Dynamic forms**: Generate forms automatically from model metadata
- **Admin interfaces**: Build generic CRUD interfaces
- **API documentation**: Self-documenting API schemas
- **Frontend validation**: Client-side validation rules
- **Query builders**: Dynamic filter interfaces
- **Data catalogs**: Explore available models and fields

## Architecture

Models are registered with the Metadata Generator registry, which analyzes their structure and generates standardized metadata objects. This metadata is then exposed through API endpoints for frontend consumption.

[Usage Guide](guide.md){ .md-button .md-button--primary }
