# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.metadata_model import MetadataModelRegistry


async def test_get_metadata_describes_a_model(setup_db: FastEdgy) -> None:
    metadata = await get_service(MetadataModelRegistry).get_metadata("product")

    assert metadata.api_name == "test_products"
    assert metadata.searchable is True
    assert metadata.search_field == "search_value"
    assert "name" in metadata.fields
    assert "price" in metadata.fields


async def test_get_map_models_includes_registered_models(setup_db: FastEdgy) -> None:
    models = await get_service(MetadataModelRegistry).get_map_models()

    assert "product" in models
    assert "user" in models


async def test_is_registered(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    assert await registry.is_registered("product") is True
