# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections import defaultdict

from enum import Enum

from typing import Type, Any, Callable, Union, Sequence

from fastapi.params import Depends
from fastapi.routing import APIRoute
from fastapi.types import IncEx
from fastapi.datastructures import DefaultPlaceholder

from fastedgy.api_route_model.view_transformer import BaseViewTransformer
from fastedgy.dependencies import register_service, Token
from fastedgy.orm import Model

from starlette.responses import Response
from starlette.routing import BaseRoute


class RouteModelActionOptions(dict):
    path: str | None
    endpoint: Callable[..., Any] | None
    response_model: Any | None
    status_code: int | None
    tags: list[Union[str, Enum]] | None
    dependencies: Sequence[Depends] | None
    summary: str | None
    description: str | None
    response_description: str | None
    responses: dict[Union[int, str], dict[str, Any]] | None
    deprecated: bool | None
    methods: Union[set[str], list[str]] | None
    operation_id: str | None
    response_model_include: IncEx | None
    response_model_exclude: IncEx | None
    response_model_by_alias: bool | None
    response_model_exclude_unset: bool | None
    response_model_exclude_defaults: bool | None
    response_model_exclude_none: bool | None
    include_in_schema: bool | None
    response_class: Union[Type[Response], DefaultPlaceholder] | None
    name: str | None
    route_class_override: Type[APIRoute] | None
    callbacks: list[BaseRoute] | None
    openapi_extra: dict[str, Any] | None
    generate_unique_id_function: Union[Callable[[APIRoute], str], DefaultPlaceholder]


RouteModelOptions = dict[str, bool | RouteModelActionOptions]
TypeModel = Type[Model]
TypeModels = dict[TypeModel, RouteModelOptions]


DEFAULT_ROUTE_MODEL_OPTIONS = {}


class RouteModelRegistry:
    """Registry for models that should have auto-generated API routes."""

    def __init__(self):
        self._models: TypeModels = {}

    def register_model(self, model_cls: TypeModel, options: RouteModelOptions | None = None):
        """
        Register a model for auto-generating routes.

        Args:
            model_cls: The Edgy model class to register
            options: Options for route generation, with type view in key and enabled or disabled in value
        """
        self._models[model_cls] = {**DEFAULT_ROUTE_MODEL_OPTIONS, **(options or {})}

    def get_registered_models(self) -> TypeModels:
        """Get all registered models with their options."""
        return self._models

    def is_model_registered(self, model_cls: TypeModel) -> bool:
        """Check if a model is registered."""
        return model_cls in self._models

    def get_model_options(self, model_cls: TypeModel) -> RouteModelOptions:
        """Get the options for a registered model."""
        if not self.is_model_registered(model_cls):
            raise ValueError(f"Model {model_cls.__name__} is not registered in route model registry")

        return self._models[model_cls]


class ViewTransformerRegistry:
    """Registry for api route view transformers."""

    _transformers: defaultdict[TypeModel | None, list[BaseViewTransformer]] = defaultdict(lambda: [])

    def register_transformer(self, transformer: BaseViewTransformer, model_cls: TypeModel | None = None):
        if not callable(transformer):
            raise ValueError("Transformer must be callable or BaseViewTransformer instance")

        self._transformers[model_cls].append(transformer())

    def has_transformers[T = BaseViewTransformer](self, transformer_cls: Type[T], model_cls: TypeModel, transformers: list[BaseViewTransformer] | None = None) -> bool:
        return len(self.get_transformers(transformer_cls, model_cls, transformers)) > 0

    def get_transformers[T = BaseViewTransformer](self, transformer_cls: Type[T], model_cls: TypeModel, transformers: list[BaseViewTransformer] | None = None) -> list[T]:
        if not bool(getattr(transformer_cls, '__abstractmethods__', False)):
            raise ValueError(f"Model {model_cls.__name__} is not abstract")

        final_transformers = []

        models = [None, model_cls]

        for model in models:
            if model in self._transformers:
                for transformer in self._transformers[model]:
                    if issubclass(type(transformer), transformer_cls):
                        final_transformers.append(transformer)

            if transformers:
                for tmp_transformer_cls in transformers:
                    if not callable(tmp_transformer_cls):
                        raise ValueError("Transformer must be callable or BaseViewTransformer instance")

                    tmp_transformer = tmp_transformer_cls()
                    if issubclass(type(tmp_transformer), transformer_cls):
                        final_transformers.append(tmp_transformer)

        return final_transformers


ADMIN_ROUTE_MODEL_REGISTRY_TOKEN = Token[RouteModelRegistry]("admin_route_model_registry")


register_service(RouteModelRegistry())
register_service(RouteModelRegistry(), ADMIN_ROUTE_MODEL_REGISTRY_TOKEN)
register_service(ViewTransformerRegistry())


__all__ = [
    "RouteModelActionOptions",
    "RouteModelOptions",
    "TypeModel",
    "TypeModels",
    "ADMIN_ROUTE_MODEL_REGISTRY_TOKEN",
    "DEFAULT_ROUTE_MODEL_OPTIONS",
    "RouteModelRegistry",
    "ViewTransformerRegistry",
]
