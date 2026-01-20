# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

from typing import TYPE_CHECKING, cast

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry
from fastedgy.queued_task.services.queue_hooks import (
    on_pre_create,
    on_pre_run,
    on_post_run,
)

if TYPE_CHECKING:
    from fastedgy.models.user import BaseUser as User
    from fastedgy.models.workspace import BaseWorkspace as Workspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser as WorkspaceUser

logger = logging.getLogger("hooks.workspace_context")


@on_pre_create
async def save_workspace_context(task) -> None:
    """Capture current workspace context when creating a task"""
    current_user = context.get_user()
    current_workspace = context.get_workspace()

    task.context.update(
        {
            "_workspace_id": task.context.get(
                "_workspace_id", current_workspace.id if current_workspace else None
            ),
            "_user_id": task.context.get(
                "_user_id", current_user.id if current_user else None
            ),
        }
    )


@on_pre_run
async def restore_workspace_context(task) -> None:
    """Restore workspace context before executing a task"""
    from fastedgy.http import Request
    from fastedgy.models.user import BaseUser
    from fastedgy.models.workspace import BaseWorkspace
    from fastedgy.models.workspace_user import BaseWorkspaceUser

    workspace_id = task.context.get("_workspace_id")
    user_id = task.context.get("_user_id")

    if not workspace_id and not user_id:
        return

    context.set_request(
        Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "headers": [],
            }
        )
    )

    registry = get_service(Registry)
    user_model_name = BaseUser.Meta.model_name or "User"
    workspace_model_name = BaseWorkspace.Meta.model_name or "Workspace"
    workspace_user_model_name = BaseWorkspaceUser.Meta.model_name or "WorkspaceUser"
    User = None
    WorkspaceUser = None
    Workspace = None

    if BaseUser.Meta.model_name in registry.models:
        User = cast(type["User"], registry.get_model(user_model_name))

    if BaseWorkspace.Meta.model_name in registry.models:
        Workspace = cast(type["Workspace"], registry.get_model(workspace_model_name))

    if BaseWorkspaceUser.Meta.model_name in registry.models:
        WorkspaceUser = cast(
            type["WorkspaceUser"], registry.get_model(workspace_user_model_name)
        )

    if workspace_id and Workspace:
        context.set_workspace(
            await Workspace.query.filter(
                Workspace.columns.id == workspace_id
            ).get_or_none()
        )

    if user_id and User:
        context.set_user(
            await User.query.filter(User.columns.id == user_id).get_or_none()
        )

    if workspace_id and user_id and Workspace and User and WorkspaceUser:
        context.set_workspace_user(
            await WorkspaceUser.query.filter(
                (WorkspaceUser.columns.user == user_id)
                & (WorkspaceUser.columns.workspace == workspace_id)
            ).get_or_none()
        )

    logger.debug(f"Restored workspace context for task {task.id}")


@on_post_run
async def cleanup_workspace_context(task, result=None, error=None) -> None:
    """Clean up workspace context after task execution"""
    context.set_request(None)
    logger.debug(f"Cleaned up workspace context for task {task.id}")
