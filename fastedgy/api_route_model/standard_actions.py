# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.dependencies import get_service
from fastedgy.api_route_model.action import ApiRouteActionRegistry
from fastedgy.api_route_model.actions.create_action import CreateApiRouteAction
from fastedgy.api_route_model.actions.delete_action import DeleteApiRouteAction
from fastedgy.api_route_model.actions.export_action import ExportApiRouteAction
from fastedgy.api_route_model.actions.import_action import ImportApiRouteAction
from fastedgy.api_route_model.actions.get_action import GetApiRouteAction
from fastedgy.api_route_model.actions.list_action import ListApiRouteAction
from fastedgy.api_route_model.actions.patch_action import PatchApiRouteAction


def register_standard_api_route_model_actions():
    """Register all standard api route model actions."""
    arar = get_service(ApiRouteActionRegistry)
    arar.register_action(ListApiRouteAction)
    arar.register_action(ExportApiRouteAction)
    arar.register_action(ImportApiRouteAction)
    arar.register_action(GetApiRouteAction)
    arar.register_action(CreateApiRouteAction)
    arar.register_action(PatchApiRouteAction)
    arar.register_action(DeleteApiRouteAction)


__all__ = [
    "register_standard_api_route_model_actions",
]
