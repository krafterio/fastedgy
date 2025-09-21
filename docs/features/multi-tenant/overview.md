# Multi Tenant

FastEdgy is fully compatible with [Edgy ORM's multi-tenancy system](https://edgy.dymmond.com/tenancy/edgy), supporting all three multi-tenant architectures: shared schemas, separate schemas, and separate databases.

## Compatibility with Edgy ORM

FastEdgy leverages Edgy ORM's comprehensive multi-tenancy features:

- **Schema-based tenancy**: Use different database schemas per tenant
- **Database-based tenancy**: Separate databases for complete isolation
- **Shared schema tenancy**: Single schema with tenant-specific data filtering
- **Context management**: Automatic tenant context handling with `with_tenant()`
- **Dynamic queries**: Tenant-aware queries using `using()` and `using_with_db()`

For complete details on implementation, see the [Edgy ORM Tenancy documentation](https://edgy.dymmond.com/tenancy/edgy).

## FastEdgy workspace helpers

FastEdgy provides additional helpers for shared schema multi-tenancy through the workspace system:

### WorkspaceableMixin
A convenient mixin that automatically adds workspace isolation to your models:

- **Automatic workspace field**: Adds a foreign key to the current workspace
- **Context-aware saves**: Automatically assigns records to the current workspace
- **Workspace managers**: Built-in query managers that filter by workspace context

### Workspace system
FastEdgy includes a built-in workspace system for tenant management:

- **BaseWorkspace model**: Ready-to-use workspace model with name, slug, and image
- **WorkspaceableMixin**: Easy multi-tenant model inheritance
- **Context integration**: Seamless integration with FastEdgy's context system

## Use cases

- **SaaS applications**: Isolate customer data by workspace/organization
- **Enterprise applications**: Department or team-based data segregation
- **Multi-client APIs**: Serve different clients from the same application
- **Development environments**: Separate staging/production data

[Usage Guide](guide.md){ .md-button .md-button--primary }
