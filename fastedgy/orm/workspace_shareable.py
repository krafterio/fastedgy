# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Workspace Shareable records.

A *workspace shareable record* is a root model (e.g. a project) that defines its
own members and whose context can be entered per request (the ``X-Workspace-Shared-Record``
header): the request then runs as the record's workspace (run-as), every
workspaceable query is confined to the record subtree declared through
``Meta.workspace_shareable_via`` paths (deny by default), and permissions can be
resolved from the membership row exposed in the context params.

Declaration surface:

- root model: ``WorkspaceShareableMixin`` + ``Meta.workspace_shareable_key`` and the
  overridable classmethod hooks ``workspace_shareable_authorize`` /
  ``workspace_shareable_visibility_filter`` (business semantics stay app-side);
- member model: ``WorkspaceShareableMemberMixin`` + ``Meta.workspace_shareable_record_field``
  (and optionally ``workspace_shareable_user_field``, default ``"user"``);
- children: ``@workspace_shareable_via(<root model>, "<path.to.root>")`` — the root
  reference is a class, a name string (Edgy ``ForeignKey("Project")`` style) or a
  lambda; the scope key never appears on children (derived from the root). The
  root's own ``"id"`` path is implicit.

Runtime surface: header ``X-Workspace-Shared-Record: <key>:<id>``, context params
``workspace_shared_record`` / ``workspace_shared_record_member``, dependency
``get_workspace_shared_record`` and helper ``resolve_workspace_shared_record``.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from fastedgy.dependencies import get_service, register_service

if TYPE_CHECKING:
    from fastedgy.orm import Model
    from fastedgy.orm.filter.types import Filter


WORKSPACE_SHARED_RECORD_HEADER = "X-Workspace-Shared-Record"


_C = TypeVar("_C", bound=type)


def snake_case(name: str) -> str:
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class WorkspaceShareableRoot:
    def __init__(self, key: str, root_model: type["Model"]):
        self.key = key
        self.root_model = root_model
        self.member_model: type["Model"] | None = None
        self.member_record_field: str = ""
        self.member_user_field: str = "user"


class WorkspaceShareableRegistry:
    """Registry of workspace-shareable root models, their member models and the
    ``workspace_shareable_via`` paths declared by children."""

    def __init__(self) -> None:
        self._roots: dict[str, WorkspaceShareableRoot] = {}
        self._pending_members: list[type["Model"]] = []
        self._children: dict[type, list[str]] = {}
        self._paths: dict[tuple[type, str], str | None] = {}

    def register_root(self, model_cls: type["Model"], key: str) -> None:
        existing = self._roots.get(key)

        if existing is not None and existing.root_model is not model_cls:
            raise RuntimeError(
                f"Workspace shareable key '{key}' is already registered by {existing.root_model.__name__}"
            )

        self._roots[key] = WorkspaceShareableRoot(key, model_cls)
        self._paths.clear()

    def register_member(self, member_cls: type["Model"]) -> None:
        self._pending_members.append(member_cls)

    def register_child(self, model_cls: type, path: str) -> None:
        self._children.setdefault(model_cls, []).append(path)
        self._paths.clear()

    def roots(self) -> dict[str, WorkspaceShareableRoot]:
        self._link_members()

        return dict(self._roots)

    def get_root(self, key: str) -> WorkspaceShareableRoot | None:
        self._link_members()

        return self._roots.get(key)

    def path_for(self, model_cls: type, key: str) -> str | None:
        cache_key = (model_cls, key)

        if cache_key in self._paths:
            return self._paths[cache_key]

        root = self._roots.get(key)

        if root is not None and issubclass(model_cls, root.root_model):
            self._paths[cache_key] = "id"

            return "id"

        unresolved = False

        for klass in model_cls.__mro__:
            for path in self._children.get(klass, ()):
                resolved = self._resolve_path_root(klass, path)

                if resolved is None:
                    unresolved = True
                elif resolved.key == key:
                    self._paths[cache_key] = path

                    return path

        if not unresolved:
            self._paths[cache_key] = None

        return None

    def has_paths(self, model_cls: type) -> bool:
        return any(klass in self._children for klass in model_cls.__mro__) or any(
            issubclass(model_cls, root.root_model) for root in self._roots.values()
        )

    def _resolve_path_root(self, model_cls: type, path: str) -> WorkspaceShareableRoot | None:
        """The root is derived from the path itself: the FK target of the last
        segment. Lazy — FK targets are strings until Edgy resolves them."""
        current: type | None = model_cls

        for segment in path.split("."):
            meta = getattr(current, "meta", None)
            field = meta.fields.get(segment) if meta is not None else None
            target = getattr(field, "target", None)

            if not isinstance(target, type):
                return None

            current = target

        for root in self._roots.values():
            if current is not None and issubclass(current, root.root_model):
                return root

        return None

    def _link_members(self) -> None:
        """FK targets are declared as strings and resolved by Edgy after all the
        models are registered — member↔root linking is therefore lazy. The record
        field is auto-detected (the FK whose target is a registered root), with
        ``Meta.workspace_shareable_record_field`` as an explicit override."""
        if not self._pending_members:
            return

        remaining: list[type["Model"]] = []

        for member_cls in self._pending_members:
            meta = getattr(member_cls, "Meta", None)
            explicit = getattr(meta, "workspace_shareable_record_field", None)
            linked = False
            unresolved = False

            for name, field in member_cls.meta.fields.items():
                if explicit and name != explicit:
                    continue

                target = getattr(field, "target", None)

                if target is not None and not isinstance(target, type):
                    unresolved = True
                    continue

                if not isinstance(target, type):
                    continue

                for root in self._roots.values():
                    if issubclass(target, root.root_model) or issubclass(root.root_model, target):
                        root.member_model = member_cls
                        root.member_record_field = name
                        root.member_user_field = getattr(meta, "workspace_shareable_user_field", "user")
                        linked = True

            if not linked and unresolved:
                remaining.append(member_cls)

        self._pending_members = remaining


register_service(WorkspaceShareableRegistry)


def workspace_shareable_via(path: str) -> Callable[[_C], _C]:
    """Declare the path binding a child model to its workspace-shareable root.

    The root model is derived from the path itself (the FK target of its last
    segment), so neither the root nor the scope key appears on children.

        @workspace_shareable_via("expense_project.project")
        class Expense(BaseModel, WorkspaceableMixin): ...
    """

    def decorator(cls: _C) -> _C:
        get_service(WorkspaceShareableRegistry).register_child(cls, path)

        return cls

    return decorator


def enforce_shared_record_write(instance: Any, scope: tuple[str, int]) -> None:
    """Write-path containment: stamp/validate the direct FK to the shared record,
    deny writes on models that declared no path (deny by default). Multi-segment
    paths are validated transitively by ``validate_write_references`` (the
    intermediate FK must be visible through the confined ``.query``)."""
    from fastedgy.i18n import _t
    from fastedgy.orm.access_guard import AccessDeniedError

    key, record_id = scope
    registry = get_service(WorkspaceShareableRegistry)
    path = registry.path_for(type(instance), key)

    if path is None:
        raise AccessDeniedError(detail=_t("This resource is not available in a shared record context."))

    if path == "id":
        if getattr(instance, "pk", None) != record_id:
            raise AccessDeniedError(detail=_t("You do not have access to this resource."))

        return

    if "." in path:
        return

    current = getattr(instance, path, None)
    pk = _reference_pk(current)

    if pk is None:
        setattr(instance, path, record_id)
    elif pk != record_id:
        raise AccessDeniedError(detail=_t("You do not have access to this resource."))


async def resolve_workspace_shared_record(instance: Any, key: str) -> Any | None:
    """Walk the declared ``workspace_shareable_via`` path from an instance up to
    its shared root record (re-query at each hop — never a lazy load). Returns
    ``None`` when the model declares no path or any hop is unset."""
    registry = get_service(WorkspaceShareableRegistry)
    path = registry.path_for(type(instance), key)

    if path is None:
        return None

    if path == "id":
        return instance

    current: Any = instance

    for segment in path.split("."):
        field = type(current).meta.fields.get(segment)
        target = getattr(field, "target", None)

        if not isinstance(target, type):
            return None

        pk = _reference_pk(getattr(current, segment, None))

        if pk is None:
            return None

        current = await target.global_query.filter(pk=pk).first()

        if current is None:
            return None

    return current


def shared_record_confinement_filter(model_cls: type) -> "Filter | None":
    """Global filter (registered on ``WorkspaceableMixin``): inside a shared-record
    context, a model is only queryable through its declared path — and strictly
    confined to the records of that shared root. No declaration = no rows."""
    from fastedgy import context
    from fastedgy.orm.filter import R

    scope = context.get_param("workspace_shared_record")

    if not scope:
        return None

    key, record_id = scope
    registry = get_service(WorkspaceShareableRegistry)
    path = registry.path_for(model_cls, key)

    if path is None:
        return R("id", "=", 0)

    if path == "id":
        return R("id", "=", record_id)

    return R(path, "=", record_id)


def shared_record_cascade_filter(model_cls: type) -> "Filter | None":
    """Global filter (registered on ``WorkspaceableMixin``): outside any shared-record
    context, children of a shareable root stay subject to the root's visibility
    predicate (``workspace_shareable_visibility_filter`` hook, app-side semantics)."""
    from fastedgy import context

    if context.get_param("workspace_shared_record"):
        return None

    if context.get_user() is None:
        return None

    registry = get_service(WorkspaceShareableRegistry)

    for root in registry.roots().values():
        path = registry.path_for(model_cls, root.key)

        if path is None or path == "id":
            continue

        hook = getattr(root.root_model, "workspace_shareable_visibility_filter", None)

        if hook is None:
            continue

        filters = hook(path)

        if filters is not None:
            return filters

    return None


def shared_record_filter_applies(model_cls: type) -> bool:
    from fastedgy import context

    return not context.get_param("skip_access_control")


def _reference_pk(value: Any) -> Any:
    from fastedgy.orm.fields import BaseFieldType

    if value is None or isinstance(value, BaseFieldType):
        return None

    return getattr(value, "pk", value)


__all__ = [
    "WORKSPACE_SHARED_RECORD_HEADER",
    "WorkspaceShareableRegistry",
    "WorkspaceShareableRoot",
    "workspace_shareable_via",
    "enforce_shared_record_write",
    "resolve_workspace_shared_record",
    "shared_record_confinement_filter",
    "shared_record_cascade_filter",
    "shared_record_filter_applies",
]
