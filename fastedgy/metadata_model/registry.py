# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.dependencies import register_service
from fastedgy.metadata_model.generator import generate_metadata_model, add_inverse_relations
from fastedgy.orm import Model
from fastedgy.schemas.dataset import MetadataModel

TypeMetadataModels = dict[Model, MetadataModel]
TypeMapMetadataModels = dict[str, MetadataModel]


class MetadataModelRegistry:
    def __init__(self):
        self._models: TypeMetadataModels = {}
        self._map_names: dict[str, Model] = {}
        self._lazy_models: list[Model] = []

    async def load_models(self) -> None:
        if not self._lazy_models:
            return

        for model_cls in self._lazy_models:
            self._models[model_cls] = await generate_metadata_model(model_cls)
            self._map_names[str(model_cls.meta.tablename)] = model_cls

        add_inverse_relations(self._models)

    def register_model(self, model_cls: Model):
        """
        Register a model for metadata exposure.
        """
        self._lazy_models.append(model_cls)

    async def get_models(self) -> TypeMetadataModels:
        """Get all registered models with their options."""
        await self.load_models()

        return self._models

    async def get_map_models(self) -> TypeMapMetadataModels:
        """Get all registered models with their options."""
        maps = {}

        for metadata in (await self.get_models()).values():
            maps[metadata.name] = metadata

        return maps

    async def is_registered(self, model_cls: Model | str) -> bool:
        """Check if a model is registered for metadata."""
        await self.load_models()

        if isinstance(model_cls, str):
            if model_cls not in self._map_names:
                return False

            model_cls = self._map_names[model_cls]

        return model_cls in self._models

    async def get_metadata(self, model_cls: Model | str) -> MetadataModel:
        """
        Get a model by its name.

        Raises:
            ValueError: If the model is not found
        """
        if await self.is_registered(model_cls):
            if isinstance(model_cls, str):
                model_cls = self._map_names[model_cls]

            return self._models[model_cls]

        raise ValueError(f"Model {str(model_cls)} not found in metadata registry")

    async def get_model_from_metadata(self, metadata: MetadataModel | str) -> Model:
        await self.load_models()

        if isinstance(metadata, str):
            metadata = await self.get_metadata(metadata)

        for model, model_metadata in self._models.items():
            if metadata == model_metadata:
                return model

        raise ValueError(f"Model {metadata.name} does not exist")


register_service(lambda: MetadataModelRegistry(), MetadataModelRegistry)

__all__ = [
    "MetadataModelRegistry",
    "TypeMetadataModels",
    "TypeMapMetadataModels",
]
