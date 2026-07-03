# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from contextlib import contextmanager
from contextvars import ContextVar, Token
from enum import Enum
from typing import TYPE_CHECKING, Any, Generator, Union
from zoneinfo import ZoneInfo

from fastedgy.timezone import get_timezone_info

if TYPE_CHECKING:
    from fastedgy.http import Request
    from fastedgy.models.workspace_extra_field import (
        BaseWorkspaceExtraField as WorkspaceExtraField,
    )
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser as WorkspaceUser


_current_request: ContextVar[Union["Request", None]] = ContextVar("current_request", default=None)


def set_request(request: Union["Request", None]) -> Token:
    return _current_request.set(request)


def get_request() -> Union["Request", None]:
    return _current_request.get()


def reset_request(token: Token) -> None:
    _current_request.reset(token)


def set_timezone(timezone: str | ZoneInfo) -> None:
    req = get_request()
    if req:
        req.state.timezone = ZoneInfo(timezone) if isinstance(timezone, str) else timezone


def has_timezone() -> bool:
    req = get_request()
    return req is not None and hasattr(req.state, "timezone") and req.state.timezone is not None


def get_timezone() -> ZoneInfo:
    req = get_request()

    if req and hasattr(req.state, "timezone"):
        return req.state.timezone

    return get_timezone_info()


def set_locale(locale: str) -> None:
    req = get_request()
    if req:
        req.state.locale = locale


def get_locale() -> str:
    from fastedgy.dependencies import get_service
    from fastedgy.config import BaseSettings

    req = get_request()

    if req and hasattr(req.state, "locale"):
        return req.state.locale

    return get_service(BaseSettings).fallback_locale


def set_user(user: Union["User", None]) -> None:
    req = get_request()
    if req:
        req.state.user = user


def get_user() -> Union["User", None]:
    req = get_request()

    return req.state.user if req and hasattr(req.state, "user") else None


def get_user_id() -> Union[int, None]:
    user = get_user()
    return user.id if user else None


def set_workspace(workspace: Union["Workspace", None]) -> None:
    req = get_request()
    if req:
        req.state.workspace = workspace


def get_workspace() -> Union["Workspace", None]:
    req = get_request()

    return req.state.workspace if req and hasattr(req.state, "workspace") else None


def get_workspace_id() -> Union[int, None]:
    workspace = get_workspace()
    return workspace.id if workspace else None


def set_workspace_user(workspace_user: Union["WorkspaceUser", None]) -> None:
    req = get_request()
    if req:
        req.state.workspace_user = workspace_user


def get_workspace_user() -> Union["WorkspaceUser", None]:
    req = get_request()

    return req.state.workspace_user if req and hasattr(req.state, "workspace_user") else None


def set_workspace_extra_fields(
    extra_fields: list["WorkspaceExtraField"] | None,
) -> None:
    fields_map: dict["Enum", list["WorkspaceExtraField"]] | None = None

    if extra_fields:
        fields_map = {}

        for field in extra_fields:
            if not field.model:
                continue

            if field.model.value not in fields_map:
                fields_map[field.model.value] = []

            fields_map[field.model.value].append(field)

    req = get_request()
    if req:
        req.state.workspace_extra_fields = fields_map


def get_workspace_extra_fields(
    model_name: str | None = None,
) -> list["WorkspaceExtraField"]:
    req = get_request()
    all_fields = []
    current_fields = (
        req.state.workspace_extra_fields if req and hasattr(req.state, "workspace_extra_fields") else None
    ) or {}

    if not model_name:
        for fields in current_fields.values():
            all_fields.append(*fields)
    else:
        if model_name in current_fields:
            all_fields.append(*current_fields[model_name])

    return all_fields


def get_map_workspace_extra_fields(model_name: str) -> dict[str, "WorkspaceExtraField"]:
    fields = get_workspace_extra_fields(model_name)

    return {str(field.name): field for field in fields}


_params: ContextVar[dict[str, Any]] = ContextVar("context_params", default={})


@contextmanager
def params(**values: Any) -> Generator[None, None, None]:
    """Scope extra context parameters to a `with` block.

    Available anywhere via `get_param(...)` for the duration of the block
    (request, queue task or plain call), then automatically restored. Lets a
    trusted flow toggle a global filter from its `apply` predicate:

        with context.params(skip_access_control=True):
            await membership.save()
    """
    token = _params.set({**_params.get(), **values})

    try:
        yield
    finally:
        _params.reset(token)


def get_param(name: str, default: Any = None) -> Any:
    return _params.get().get(name, default)


def get_params() -> dict[str, Any]:
    return dict(_params.get())


__all__ = [
    "set_request",
    "get_request",
    "reset_request",
    "set_timezone",
    "get_timezone",
    "set_locale",
    "get_locale",
    "set_user",
    "get_user",
    "set_workspace",
    "get_workspace",
    "set_workspace_user",
    "get_workspace_user",
    "set_workspace_extra_fields",
    "get_workspace_extra_fields",
    "get_map_workspace_extra_fields",
    "params",
    "get_param",
    "get_params",
]
