# Multi Tenant - Usage guide

## Using WorkspaceableMixin

### Add workspace support to models
The simplest way to make a model workspace-aware is to use the `WorkspaceableMixin`:

```python
from fastedgy.orm import Model, fields
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.models.base import BaseModel


class Product(BaseModel, WorkspaceableMixin):
    name = fields.CharField(max_length=100)
    price = fields.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        tablename = "products"
```

### Automatic workspace assignment
Models with `WorkspaceableMixin` automatically get assigned to the current workspace:

- **Workspace field**: Foreign key relationship added automatically
- **Context-aware saves**: Records saved to the current workspace context
- **Filtered queries**: Default queries only return workspace-specific records

### Workspace managers
FastEdgy provides specialized managers for workspace-aware queries:

- **`query`**: Returns only records from the current workspace
- **`global_query`**: Returns records from all workspaces (admin use)

## Basic workspace operations

### Create workspace-scoped records
```python
# Within workspace context, records are automatically scoped
product = await Product.query.create(name="Laptop", price=999.99)
```

### Query workspace-specific data
```python
# Only returns products from the current workspace
products = await Product.query.all()

# Access all products across workspaces (admin)
all_products = await Product.global_query.all()
```

## Advanced multi-tenancy

For advanced multi-tenancy patterns including schema-based and database-based tenancy, refer to the comprehensive [Edgy ORM Tenancy documentation](https://edgy.dymmond.com/tenancy/edgy).

Key Edgy ORM features available in FastEdgy:

- **`using(schema=...)`**: Query specific database schemas
- **`using_with_db(...)`**: Query different databases
- **`with_tenant(...)`**: Set global tenant context
- **Schema management**: Automatic schema creation and management

## Workspace from the URL

`get_current_workspace` reads the workspace of a request from its path, checks that the current
user is a member of it, and sets the workspace, the membership and the custom fields in the
context. A router scoped to a workspace declares the path parameter and the dependency once:

```python
from fastapi import APIRouter, Depends

from fastedgy.api_route_model.router import register_api_route_models
from fastedgy.depends.security import get_current_user, get_current_workspace

router = APIRouter(
    prefix="/api/{workspace}",
    dependencies=[Depends(get_current_user), Depends(get_current_workspace)],
)
register_api_route_models(router)
```

A slug the user is not a member of answers 404.

### Naming the path parameter

`workspace_path_param` names the parameter, `workspace` by default. An application that calls its
workspaces something else keeps its own word in its URLs:

```python
from fastedgy.config import BaseSettings


class Settings(BaseSettings):
    workspace_path_param: str = "household"
```

### The default workspace

Each user has a default workspace: the membership marked with `is_default`, or the oldest one while
none is marked. A membership that goes, even through a database cascade, never leaves a user without
one. `workspace_default_slug` names a slug that stands for it, for a client that does not know which
workspace it is in:

```python
from fastedgy.config import BaseSettings


class Settings(BaseSettings):
    workspace_default_slug: str | None = "legacy"
```

`/api/legacy/...` then reaches the default workspace of whoever calls it. The mark is out of reach of
the API and of regular saves: `make_default()` sets it and clears the previous one.

```python
default = await WorkspaceUser.default_for(user.id)

await other_membership.make_default()
```

## Members of the workspace

The user model belongs to every workspace at once, so it has no generated route inside one. A
relation to a user (an owner, an assignee) still needs its records listed and searched from inside
the workspace: `create_workspace_users_router` serves the members of the current workspace, through
the generated list and get actions. Pagination, ordering, `X-Fields` and `X-Filter` behave as on any
other model.

```python
from fastapi import APIRouter, Depends

from fastedgy.api.workspace_users import create_workspace_users_router
from fastedgy.depends.security import get_current_user, get_current_workspace

router = APIRouter(
    prefix="/api/{workspace}",
    dependencies=[Depends(get_current_user), Depends(get_current_workspace)],
)
router.include_router(create_workspace_users_router())
```

`GET /api/{workspace}/users` lists the members, `GET /api/{workspace}/users/{id}` reads one; a user
of another workspace answers 404. The routes start from `workspace_members(workspace)`, the users
holding a membership through the `workspace_memberships` relation every workspace user model
declares. An application that serves more than the memberships passes its own query:

```python
from fastedgy.api.workspace_users import create_workspace_users_router
from fastedgy.orm.filter import Or, R


def members_and_system(workspace):
    return User.query.filter(
        Or(R("workspace_memberships.workspace", "=", workspace.id), R("id", "=", SYSTEM_USER_ID)),
        allow_excluded=True,
    )


router.include_router(create_workspace_users_router(members=members_and_system))
```

`members` may also be a coroutine function, for a query that needs a read first.

## Configuration

Workspace multi-tenancy works with FastEdgy's context system. The workspace context is typically set by:

- **Authentication middleware**: Set workspace based on user credentials
- **API headers**: Extract workspace from request headers
- **URL routing**: Determine workspace from URL patterns

[Back to Overview](overview.md){ .md-button }
