# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.metadata_model.generator import (
    add_inverse_relations,
    apply_workspace_extra_fields,
    generate_metadata_model,
)
from fastedgy.models.base import BaseModel, BaseView
from fastedgy.schemas.dataset import MetadataModel

TypeMetadataModels = dict[type[BaseModel | BaseView], MetadataModel]
TypeMapMetadataModels = dict[str, MetadataModel]


class MetadataModelRegistry:
    def __init__(self):
        self._model_classes: list[type[BaseModel | BaseView]] = []
        self._models_by_locale: dict[str, TypeMetadataModels] = {}
        self._map_names: dict[str, type[BaseModel | BaseView]] = {}
        self._lazy_models: list[type[BaseModel | BaseView]] = []

    async def load_models(self) -> TypeMetadataModels:
        from fastedgy.context import get_locale

        if self._lazy_models:
            self._model_classes.extend(self._lazy_models)
            self._lazy_models = []
            self._models_by_locale = {}

        # Labels are rendered while the metadata is generated, so each locale needs its own copy.
        locale = get_locale()
        models = self._models_by_locale.get(locale)

        if models is None:
            models = {}

            for model_cls in self._model_classes:
                models[model_cls] = await generate_metadata_model(model_cls)
                self._map_names[str(model_cls.meta.tablename)] = model_cls
                self._map_names[models[model_cls].name] = model_cls

            add_inverse_relations(models)
            self._models_by_locale[locale] = models

        return models

    def register_model(self, model_cls: type[BaseModel | BaseView]):
        """
        Register a model for metadata exposure.
        """
        self._lazy_models.append(model_cls)

    async def get_models(self) -> TypeMetadataModels:
        """Get all registered models with their options."""
        return await self.load_models()

    async def get_map_models(self) -> TypeMapMetadataModels:
        """Get all registered models with their options."""
        from fastedgy import context

        maps = {}
        by_model = context.get_workspace_extra_fields_by_model()

        for metadata in (await self.get_models()).values():
            maps[metadata.name] = apply_workspace_extra_fields(metadata, by_model.get(metadata.name, []))

        return maps

    async def is_registered(self, model_cls: type[BaseModel | BaseView] | str) -> bool:
        """Check if a model is registered for metadata."""
        models = await self.load_models()

        if isinstance(model_cls, str):
            if model_cls not in self._map_names:
                return False

            model_cls = self._map_names[model_cls]

        return model_cls in models

    async def get_metadata(self, model_cls: type[BaseModel | BaseView] | str) -> MetadataModel:
        """
        Get a model by its name.

        Raises:
            ValueError: If the model is not found
        """
        if await self.is_registered(model_cls):
            if isinstance(model_cls, str):
                model_cls = self._map_names[model_cls]

            return apply_workspace_extra_fields((await self.load_models())[model_cls])

        raise ValueError(f"Model {model_cls!s} not found in metadata registry")

    async def get_model_from_name(self, name: str) -> type[BaseModel | BaseView] | None:
        """Resolve a model class from its metadata name or tablename."""
        await self.load_models()

        return self._map_names.get(name)

    async def get_model_from_metadata(self, metadata: MetadataModel | str) -> type[BaseModel | BaseView]:
        await self.load_models()

        if isinstance(metadata, str):
            metadata = await self.get_metadata(metadata)

        model = self._map_names.get(metadata.name)

        if model is not None:
            return model

        for model, model_metadata in (await self.load_models()).items():
            if metadata == model_metadata:
                return model

        raise ValueError(f"Model {metadata.name} does not exist")


__all__ = [
    "MetadataModelRegistry",
    "TypeMapMetadataModels",
    "TypeMetadataModels",
]
