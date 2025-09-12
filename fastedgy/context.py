# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Union

from starlette.requests import Request

if TYPE_CHECKING:
    from fastedgy.models.workspace_extra_field import BaseWorkspaceExtraField as WorkspaceExtraField, WorkspaceExtraModelType
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser as WorkspaceUser


_current_request: ContextVar[Request | None] = ContextVar("current_request", default=None)


def set_request(request: Request | None) -> Token:
    return _current_request.set(request)


def get_request() -> Request | None:
    return _current_request.get()


def reset_request(token: Token) -> None:
    _current_request.reset(token)


def set_user(user: Union["User", None]) -> None:
    req = get_request()
    if req:
        req.state.user = user


def get_user() -> Union["User", None]:
    req = get_request()

    return req.state.user if req and hasattr(req.state, "user") else None


def set_workspace(workspace: Union["Workspace", None]) -> None:
    req = get_request()
    if req:
        req.state.workspace = workspace


def get_workspace() -> Union["Workspace", None]:
    req = get_request()

    return req.state.workspace if req and hasattr(req.state, "workspace") else None


def set_workspace_user(workspace_user: Union["WorkspaceUser", None]) -> None:
    req = get_request()
    if req:
        req.state.workspace_user = workspace_user


def get_workspace_user() -> Union["WorkspaceUser", None]:
    req = get_request()

    return req.state.workspace_user if req and hasattr(req.state, "workspace_user") else None


def set_workspace_extra_fields(extra_fields: list["WorkspaceExtraField"] | None) -> None:
    fields_map: dict["WorkspaceExtraModelType", list["WorkspaceExtraField"]] | None = None

    if extra_fields:
        fields_map = {}

        for field in extra_fields:
            if not field.model:
                continue

            if field.model not in fields_map:
                fields_map[field.model] = []

            fields_map[field.model].append(field)

    req = get_request()
    if req:
        req.state.workspace_extra_fields = fields_map


def get_workspace_extra_fields(model_name: str | None = None) -> list["WorkspaceExtraField"]:
    from fastedgy.models.workspace_extra_field import WorkspaceExtraModelType

    req = get_request()
    all_fields = []
    current_fields = (req.state.workspace_extra_fields if req and hasattr(req.state, "workspace_extra_fields") else None) or {}

    if not model_name:
        for fields in current_fields.values():
            all_fields.append(*fields)
    else:
        name = WorkspaceExtraModelType[model_name]

        if name in current_fields:
            all_fields.append(*current_fields[name])

    return all_fields


def get_map_workspace_extra_fields(model_name: str) -> dict[str, "WorkspaceExtraField"]:
    fields = get_workspace_extra_fields(model_name)

    return {str(field.name): field for field in fields}
