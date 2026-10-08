# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING, Any, cast

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.models.custom_view import CustomViewMixin, custom_view_place, find_custom_view_model, key_of
from fastedgy.orm import Registry, fields
from fastedgy.orm.filter import And, R, global_filter
from fastedgy.orm.registry import find_lazy_model, has_lazy_model
from fastedgy.orm.signals import post_save, pre_save

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User


def _own_favorites() -> Any:
    user_id = context.get_user_id()

    if user_id is None:
        return None

    view_model = find_custom_view_model()

    if view_model is not None and "workspace" in view_model.meta.fields:
        return And(R("user", "=", user_id), custom_view_place(context.get_workspace_id(), "view.workspace"))

    return R("user", "=", user_id)


@global_filter(_own_favorites)
class CustomViewFavoriteMixin(BaseModel):
    """The view a user opens a list on, whichever the list opens on for
    everyone. One per user and per list: marking one unmarks the previous."""

    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Favorite view")
        label_plural = _ts("Favorite views")

    user: "User | None" = fields.ForeignKey(
        "User",
        null=True,
        on_delete="CASCADE",
        related_name=False,
        read_only=True,
        label=_ts("User"),
    )


class BaseCustomViewFavorite(CustomViewFavoriteMixin):
    class Meta(CustomViewFavoriteMixin.Meta):
        abstract = True


def register_default_custom_view_favorite_model() -> None:
    """Declare the concrete model unless the app declared its own. Its view key
    points at the custom view model the application ended with."""
    if has_lazy_model(CustomViewFavoriteMixin):
        return

    view_model = find_lazy_model(CustomViewMixin)

    if view_model is None:
        return

    from fastedgy.api_route_model import api_route_model
    from fastedgy.api_route_model.decorators import console_api_route_model

    view_model_name = view_model.__name__
    actions = {"import": False, "import_template": False, "export": False}

    @console_api_route_model(actions=actions)
    @api_route_model(actions=actions)
    class CustomViewFavorite(BaseCustomViewFavorite):
        class Meta:
            tablename = "custom_view_favorites"
            label = _ts("Favorite view")
            label_plural = _ts("Favorite views")
            indexes = [
                fields.Index(fields=["user"], suffix="idx_custom_view_favorites"),
                fields.Index(fields=["view"], suffix="idx_custom_view_favorites"),
            ]
            unique_together = [("user", "view")]

        view = fields.ForeignKey(
            view_model_name,
            on_delete="CASCADE",
            related_name="favorites",
            label=_ts("View"),
        )


def find_custom_view_favorite_model() -> type[CustomViewFavoriteMixin] | None:
    for model in get_service(Registry).models.values():
        if (
            isinstance(model, type)
            and issubclass(model, CustomViewFavoriteMixin)
            and not getattr(model, "__is_proxy_model__", False)
            and not model.meta.abstract
        ):
            return cast(type[CustomViewFavoriteMixin], model)

    return None


async def _stamp_owner(
    sender: type[CustomViewFavoriteMixin],
    instance: Any,
    model_instance: Any = None,
    values: dict[str, Any] | None = None,
    column_values: dict[str, Any] | None = None,
    is_update: bool = False,
    **kwargs: Any,
) -> None:
    favorite = model_instance if model_instance is not None else instance
    user = context.get_user()

    if is_update or user is None or not isinstance(favorite, CustomViewFavoriteMixin):
        return

    favorite.user = user

    for written in (values, column_values):
        if written is not None:
            written["user"] = key_of(user)


async def _keep_one_favorite(
    sender: type[CustomViewFavoriteMixin],
    instance: Any,
    model_instance: Any = None,
    **kwargs: Any,
) -> None:
    favorite = model_instance if model_instance is not None else instance
    view_model = find_custom_view_model()

    if view_model is None or not isinstance(favorite, CustomViewFavoriteMixin):
        return

    view = await view_model.global_query.filter(R("id", "=", key_of(getattr(favorite, "view", None)))).first()

    if view is None:
        return

    rules = [
        R("user", "=", key_of(getattr(favorite, "user", None))),
        R("view.model", "=", view.model),
        R("view.scope", "=", view.scope or ""),
        R("id", "!=", favorite.id),
    ]

    if "workspace" in view_model.meta.fields:
        rules.append(custom_view_place(key_of(getattr(view, "workspace", None)), "view.workspace"))

    for other in await sender.global_query.filter(And(*rules)).all():
        await other.delete()


_signalled: set[type] = set()


def register_custom_view_favorite_signals() -> None:
    model = find_custom_view_favorite_model()

    if model is None or model in _signalled:
        return

    _signalled.add(model)

    pre_save.connect_via(model)(_stamp_owner)
    post_save.connect_via(model)(_keep_one_favorite)


__all__ = [
    "BaseCustomViewFavorite",
    "CustomViewFavoriteMixin",
    "find_custom_view_favorite_model",
    "register_custom_view_favorite_signals",
    "register_default_custom_view_favorite_model",
]
