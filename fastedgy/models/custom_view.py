# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, status

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.i18n import _t, _ts
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import BlameableMixin
from fastedgy.orm import Registry, fields
from fastedgy.orm.filter import And, Or, R, global_filter
from fastedgy.orm.order_by import OrderByList
from fastedgy.orm.registry import find_lazy_model, has_lazy_model
from fastedgy.orm.signals import post_save, pre_delete, pre_save
from fastedgy.schemas import computed_field, computed_field_deps

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User


def key_of(value: Any) -> Any:
    """The key a foreign key holds, whether it reads as a record or as its id."""
    return getattr(value, "id", value)


def custom_view_place(workspace_id: int | None, path: str = "workspace") -> Any:
    """The views of a workspace, or the global ones when there is none."""
    return R(path, "=", workspace_id) if workspace_id is not None else R(path, "is empty")


def _visible_owners() -> Any:
    user_id = context.get_user_id()

    return Or(R("user", "is empty"), R("user", "=", user_id)) if user_id is not None else R("user", "is empty")


def _visible_place() -> Any:
    return custom_view_place(context.get_workspace_id())


def _has_workspace(model_cls: type) -> bool:
    return "workspace" in cast(Any, model_cls).meta.fields


@global_filter(_visible_owners)
@global_filter(_visible_place, apply=_has_workspace)
class CustomViewMixin(BaseModel, BlameableMixin):
    """A list arranged ahead of time under a name: its filter, its order and,
    for the applications that have them, its grouping and its columns.

    A view without workspace is global (a console resolves none), else it
    belongs to one workspace; a view without user is shared, else it is its
    owner's alone. The global filter keeps both rules for reads and writes."""

    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Custom view")
        label_plural = _ts("Custom views")
        default_order_by: OrderByList = [("sequence", "asc"), ("id", "asc")]

    name: str = fields.CharField(max_length=100, label=_ts("Name"))

    model: str = fields.CharField(max_length=100, label=_ts("Model"))

    scope: str = fields.CharField(max_length=100, default="", label=_ts("Scope"))

    user: "User | None" = fields.ForeignKey(
        "User",
        null=True,
        on_delete="CASCADE",
        related_name=False,
        label=_ts("User"),
    )

    filters: list[Any] | None = fields.JSONField(null=True, label=_ts("Filters"))

    order_by: list[str] | None = fields.JSONField(null=True, label=_ts("Order"))

    group_by: str | None = fields.CharField(max_length=100, null=True, label=_ts("Grouping"))

    display_fields: list[Any] | None = fields.JSONField(null=True, label=_ts("Displayed columns"))

    sequence: int = fields.IntegerField(default=0, label=_ts("Position"))

    is_default: bool = fields.BooleanField(default=False, label=_ts("Default view"))

    @classmethod
    def can_manage_shared(cls) -> bool:
        """Whether the current user creates, changes and deletes the shared
        views. Everyone by default; an application whose workspaces have roles
        narrows it in its own model."""
        return True

    @computed_field
    @computed_field_deps("user")
    @property
    def editable(self) -> bool:
        owner_id = key_of(getattr(self, "user", None))

        if owner_id is not None:
            return owner_id == context.get_user_id()

        return type(self).can_manage_shared()


class BaseCustomView(CustomViewMixin):
    class Meta(CustomViewMixin.Meta):
        abstract = True


def register_default_custom_view_model() -> None:
    """Declare the concrete model unless the app declared its own, the way an
    app opts out of any other framework model: by subclassing it first. Its
    workspace key points at the application's workspace model, whatever its
    name."""
    if has_lazy_model(CustomViewMixin):
        return

    from fastedgy.api_route_model import api_route_model
    from fastedgy.api_route_model.decorators import console_api_route_model
    from fastedgy.models.workspace import BaseWorkspace

    workspace_cls = find_lazy_model(BaseWorkspace)
    workspace_model = workspace_cls.__name__ if workspace_cls is not None else None
    view_indexes = [fields.Index(fields=["user"], suffix="idx_custom_views")]

    if workspace_model:
        view_indexes.append(fields.Index(fields=["workspace", "model", "scope", "sequence"], suffix="idx_custom_views"))

    @console_api_route_model(actions={"import": False, "import_template": False})
    @api_route_model(actions={"import": False, "import_template": False})
    class CustomView(BaseCustomView):
        class Meta:
            tablename = "custom_views"
            label = _ts("Custom view")
            label_plural = _ts("Custom views")
            default_order_by: OrderByList = [("sequence", "asc"), ("id", "asc")]
            indexes = view_indexes

        if workspace_model:
            workspace = fields.ForeignKey(
                workspace_model,
                null=True,
                on_delete="CASCADE",
                related_name=False,
                exclude=True,
                label=_ts("Workspace"),
            )


def find_custom_view_model() -> type[CustomViewMixin] | None:
    for model in get_service(Registry).models.values():
        if (
            isinstance(model, type)
            and issubclass(model, CustomViewMixin)
            and not getattr(model, "__is_proxy_model__", False)
            and not model.meta.abstract
        ):
            return cast(type[CustomViewMixin], model)

    return None


def get_custom_view_model() -> type[CustomViewMixin]:
    model = find_custom_view_model()

    if model is None:
        raise RuntimeError(
            "No CustomView model is registered: build the application with `FastEdgy(custom_views=True)`."
        )

    return model


def _written(view: Any, column_values: dict[str, Any] | None, name: str) -> Any:
    if column_values and name in column_values:
        return column_values[name]

    return key_of(getattr(view, name, None))


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_t("You are not allowed to manage the shared views"),
    )


async def _check_custom_view(
    sender: type[CustomViewMixin],
    instance: Any,
    model_instance: Any = None,
    values: dict[str, Any] | None = None,
    column_values: dict[str, Any] | None = None,
    is_update: bool = False,
    **kwargs: Any,
) -> None:
    view = model_instance if model_instance is not None else instance

    if not isinstance(view, CustomViewMixin):
        return

    user_id = context.get_user_id()

    if not is_update and _has_workspace(sender):
        workspace = context.get_workspace()
        view.workspace = workspace

        for written in (values, column_values):
            if written is not None:
                written["workspace"] = key_of(workspace)

    owner_id = _written(view, column_values, "user")

    if user_id is not None and owner_id is not None and owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_t("A view belongs to whoever saves it, or to everyone"),
        )

    if user_id is not None and not sender.can_manage_shared():
        stored = None

        if is_update:
            stored = await sender.global_query.filter(R("id", "=", view.id)).first()

        if owner_id is None or (stored is not None and key_of(getattr(stored, "user", None)) is None):
            raise _forbidden()

    if owner_id is not None and _written(view, column_values, "is_default"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_t("A private view cannot be the default view of its list"),
        )

    from fastedgy.metadata_model import MetadataModelRegistry

    model_name = _written(view, column_values, "model")

    if not model_name or not await get_service(MetadataModelRegistry).is_registered(model_name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_t("No list answers to the model {model}", model=model_name),
        )

    rules = [
        R("model", "=", model_name),
        R("scope", "=", _written(view, column_values, "scope") or ""),
        R("name", "=", _written(view, column_values, "name")),
        R("user", "is empty") if owner_id is None else Or(R("user", "is empty"), R("user", "=", owner_id)),
    ]

    if _has_workspace(sender):
        rules.append(custom_view_place(_written(view, column_values, "workspace")))

    if getattr(view, "id", None) is not None:
        rules.append(R("id", "!=", view.id))

    if await sender.global_query.filter(And(*rules)).exists():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_t("A view of this list already has this name"),
        )


async def _keep_one_default(
    sender: type[CustomViewMixin], instance: Any, model_instance: Any = None, **kwargs: Any
) -> None:
    view = model_instance if model_instance is not None else instance

    if not isinstance(view, CustomViewMixin) or not getattr(view, "is_default", False):
        return

    rules = [
        R("model", "=", view.model),
        R("scope", "=", view.scope or ""),
        R("is_default", "is true"),
        R("id", "!=", view.id),
    ]

    if _has_workspace(sender):
        rules.append(custom_view_place(key_of(getattr(view, "workspace", None))))

    await sender.global_query.filter(And(*rules)).update(is_default=False)


async def _check_custom_view_delete(sender: type[CustomViewMixin], instance: Any, **kwargs: Any) -> None:
    view = kwargs.get("model_instance") or instance

    if not isinstance(view, CustomViewMixin) or context.get_user_id() is None:
        return

    if key_of(getattr(view, "user", None)) is None and not sender.can_manage_shared():
        raise _forbidden()


_signalled: set[type] = set()


def register_custom_view_signals() -> None:
    """Connected once the registry is up, to whichever concrete model the
    application ended with, its own or the default."""
    model = find_custom_view_model()

    if model is None or model in _signalled:
        return

    _signalled.add(model)

    pre_save.connect_via(model)(_check_custom_view)
    post_save.connect_via(model)(_keep_one_default)
    pre_delete.connect_via(model)(_check_custom_view_delete)


__all__ = [
    "BaseCustomView",
    "CustomViewMixin",
    "custom_view_place",
    "find_custom_view_model",
    "get_custom_view_model",
    "key_of",
    "register_custom_view_signals",
    "register_default_custom_view_model",
]
