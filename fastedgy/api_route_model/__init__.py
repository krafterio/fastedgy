# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model.decorators import api_route_model
from fastedgy.api_route_model.registry import TypeModel, TypeModels, RouteModelOptions


__all__ = [
    "TypeModel",
    "TypeModels",
    "RouteModelOptions",
    "api_route_model",
]
