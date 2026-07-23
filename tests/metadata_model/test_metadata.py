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


async def test_synchronizable_derives_from_the_sync_action(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    # Auto: the sync action is enabled (product) / absent (category).
    assert (await registry.get_metadata("product")).synchronizable is True
    assert (await registry.get_metadata("category")).synchronizable is False


async def test_synchronizable_override_wins_over_the_action(setup_db: FastEdgy) -> None:
    # Comment disables every public write action but forces the override.
    metadata = await get_service(MetadataModelRegistry).get_metadata("comment")

    assert metadata.synchronizable is True
