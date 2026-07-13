# Workspace Shareable

Workspace Shareable lets you share **one record — and everything attached to it — with users
from other workspaces**, without moving any data. A project, a trip, an event: the record stays
in its owner workspace, and invited users work inside it through a per-request context.

Think of it as a temporary, strictly bounded "run as": for the duration of the request, the
invited user operates in the record's workspace, but can only see and touch the subtree of that
single record.

## How it works

1. A **root model** (e.g. `Project`) declares itself shareable and gets a **member model**
   (e.g. `ProjectMember`) listing who can enter it.
2. **Child models** declare the path that links them to the root (e.g. a task belongs to a
   project through its category).
3. A request carrying the `X-Workspace-Shared-Record: project:42` header enters the context of
   record 42: the workspace is switched to the record's workspace, and every query is confined
   to that record's subtree.
4. Everything else is **denied by default**: a model that declared no path simply does not exist
   inside the context — reads return nothing, writes are rejected.

## Declare a shareable root

Add `WorkspaceShareableMixin` to a workspaceable model. Nothing else is required — the context
key is derived from the class name (`Project` → `project`):

```python
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import WorkspaceableMixin, WorkspaceShareableMixin


class Project(BaseModel, WorkspaceableMixin, WorkspaceShareableMixin):
    name = fields.CharField(max_length=200)
```

The mixin requires `WorkspaceableMixin`: entering a shared record means running as its
workspace, so the root must be workspace-scoped.

## Declare the member model

Add `WorkspaceShareableMemberMixin` to the model that stores who belongs to the record. The
foreign key to the root is detected automatically; the user field defaults to `user`:

```python
from fastedgy.models.mixins import WorkspaceShareableMemberMixin


class ProjectMember(BaseModel, WorkspaceShareableMemberMixin):
    project = fields.ForeignKey("Project", related_name="members")
    user = fields.ForeignKey("User")
```

If the detection is ambiguous (several FKs to shareable roots), pin the fields explicitly with
the Meta options `workspace_shareable_record_field` and `workspace_shareable_user_field`.

## Declare the children

Each model that belongs to the shared subtree declares its path to the root with the
`@workspace_shareable_via` decorator. The path uses the Query Builder dot syntax, and the root
is derived from the FK target of the last segment:

```python
from fastedgy.orm.workspace_shareable import workspace_shareable_via


@workspace_shareable_via("project")
class ShoppingList(BaseModel, WorkspaceableMixin):
    project = fields.ForeignKey("Project", null=True)


@workspace_shareable_via("task_category.project")
class Task(BaseModel, WorkspaceableMixin):
    task_category = fields.ForeignKey("TaskCategory")
```

The root's own path (`id`) is implicit — you never declare it.

**Deny by default**: inside a shared-record context, a workspaceable model without a declared
path is unreachable. Forgetting a declaration closes access, it never opens it.

## Enter a shared record context

Register the dependency after your workspace resolution:

```python
from fastedgy.depends.security import get_current_user, get_workspace_shared_record

router = APIRouter(
    prefix="/api",
    dependencies=[Depends(get_current_user), Depends(get_workspace_shared_record)],
)
```

Without the header, the dependency is a no-op — existing behavior is untouched. With it:

```
X-Workspace-Shared-Record: project:42
```

1. The root record is loaded, along with the caller's membership row.
2. The root's `workspace_shareable_authorize` hook decides whether the caller may enter
   (default: any member). A refusal is a **404** — the record's existence is not revealed.
3. The request now runs as the record's workspace, and every query/write is confined to the
   record's subtree.

A malformed header or an unknown key is a **400**; an unknown record is a **404**.

## Business hooks

The mixin exposes two overridable classmethods, so your app keeps full control of the semantics
(visibility rules, roles, plans…) without FastEdgy knowing about them:

```python
class Project(BaseModel, WorkspaceableMixin, WorkspaceShareableMixin):
    @classmethod
    async def workspace_shareable_authorize(cls, record, user, member) -> bool:
        """Who may enter the shared context. Default: member is not None."""
        return member is not None or record.owner == user

    @classmethod
    def workspace_shareable_visibility_filter(cls, path):
        """Optional: restrict who sees the children OUTSIDE the shared context.

        Called for every declared child model with its path to the root; return
        a filter built on that path, or None to leave the model untouched.
        """
        return Or(
            R(path, "is empty"),
            R(f"{path}.members.user.id", "=", context.get_user_id()),
        )
```

`workspace_shareable_visibility_filter` is the out-of-context counterpart of the confinement:
use it when a shared record must also hide its children from non-members **inside** its own
workspace (e.g. a private project whose lists should not appear in the workspace-wide listing).

## What is enforced

| Situation | Result |
|---|---|
| Read a declared model inside the context | Only rows belonging to the shared record |
| Read an undeclared model inside the context | No rows |
| Create on a declared model (direct FK) | The FK to the root is stamped automatically |
| Create/update with a FK pointing outside the record | 403 |
| Write on an undeclared model inside the context | 403 |
| Multi-segment paths | Validated transitively (the intermediate FK must be visible through the confined queries) |

The context also exposes what your permission layer may need, through the context params:
`workspace_shared_record` (`(key, id)`), `workspace_shared_record_instance` (the loaded root)
and `workspace_shared_record_member` (the caller's membership row, or `None`).

As everywhere in FastEdgy, `Model.global_query` and `context.params(skip_access_control=True)`
bypass the mechanism for trusted system code.

## Resolve the root from an instance

`resolve_workspace_shared_record` walks a declared path from any instance up to its root —
useful for notification targeting or business guards:

```python
from fastedgy.orm.workspace_shareable import resolve_workspace_shared_record

project = await resolve_workspace_shared_record(task, "project")
```

It returns `None` when the model declares no path or the instance is not attached to a root.

## Rename the header

The header name is a setting (`BaseSettings.workspace_shared_record_header`), so an application
can match its own vocabulary:

```python
class AppSettings(BaseSettings):
    workspace_shared_record_header: str = "X-Household-Shared-Record"
```

Once renamed, the default name is ignored.

[Back to Overview](overview.md)
