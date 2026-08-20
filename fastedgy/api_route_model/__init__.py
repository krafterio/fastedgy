# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import action, actions
from fastedgy.api_route_model.decorators import api_route_model
from fastedgy.api_route_model.registry import RouteModelOptions, TypeModel, TypeModels

__all__ = [
    "RouteModelOptions",
    "TypeModel",
    "TypeModels",
    "action",
    "actions",
    "api_route_model",
]
