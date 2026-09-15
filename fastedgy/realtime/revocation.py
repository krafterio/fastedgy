# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from fastedgy.dependencies import get_service, has_service
from fastedgy.depends.security import find_workspace_user_model
from fastedgy.models.user_api_token import find_user_api_token_model
from fastedgy.orm import Registry
from fastedgy.orm.filter import R
from fastedgy.orm.signals import post_delete, post_save, post_update
from fastedgy.orm.transaction import run_signal_side_effect
from fastedgy.realtime.broadcaster import WebSocketBroadcaster
from fastedgy.realtime.model import _column, _read

# The columns a session token names its account by: changing one leaves the
# tokens issued before standing for nobody.
TOKEN_SUBJECTS = ("email", "username")

_watched = False


def watch_revocations() -> None:
    """Have the sockets of an account checked at once when what let them in goes.

    A membership or a personal API key changed or deleted, an account deleted, or
    the email or username its session tokens name changed: every worker checks
    the sockets of that account now rather than at their next round. What goes
    through no ORM signal, a cascade in the database or a queryset write, is
    caught at that next round.
    """
    global _watched

    if _watched:
        return

    _watched = True

    for model_cls in (find_workspace_user_model(), find_user_api_token_model()):
        if model_cls is not None:
            post_save.connect_via(model_cls)(_holder_saved)
            post_update.connect_via(model_cls)(_holder_saved)
            post_delete.connect_via(model_cls)(_holder_deleted)

    user_model = get_service(Registry).models.get("User")

    if user_model is not None:
        post_save.connect_via(user_model)(_account_saved)
        post_update.connect_via(user_model)(_account_saved)
        post_delete.connect_via(user_model)(_account_deleted)


async def _holder_saved(
    sender: Any,
    instance: Any,
    model_instance: Any = None,
    is_update: bool = False,
    column_values: dict[str, Any] | None = None,
    **_: Any,
) -> None:
    if not is_update or model_instance is None:
        return

    user_id = _column(model_instance, column_values or {}, "user")

    # `update()` empties on the instance the relations it did not write.
    if user_id is None:
        users = await _read(sender, R("id", "=", model_instance.__dict__.get("id")), "user")
        user_id = users[0] if users else None

    _recheck(user_id)


async def _holder_deleted(sender: Any, instance: Any, model_instance: Any = None, **_: Any) -> None:
    if model_instance is not None:
        _recheck(_column(model_instance, {}, "user"))


async def _account_saved(
    sender: Any,
    instance: Any,
    model_instance: Any = None,
    is_update: bool = False,
    column_values: dict[str, Any] | None = None,
    **_: Any,
) -> None:
    if is_update and model_instance is not None and any(name in (column_values or {}) for name in TOKEN_SUBJECTS):
        _recheck(getattr(model_instance, "id", None))


async def _account_deleted(sender: Any, instance: Any, model_instance: Any = None, **_: Any) -> None:
    if model_instance is not None:
        _recheck(getattr(model_instance, "id", None))


def _recheck(user_id: Any) -> None:
    if user_id is None or not has_service(WebSocketBroadcaster):
        return

    run_signal_side_effect(lambda: get_service(WebSocketBroadcaster).recheck_users([user_id]), "realtime recheck")


__all__ = [
    "TOKEN_SUBJECTS",
    "watch_revocations",
]
