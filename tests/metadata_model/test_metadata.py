# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

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
    assert metadata.synchronizable_mode == "full"


async def test_synchronizable_mode_derives_from_the_sync_options(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    # sync=True defaults to a full mirror, sync={"mode": "partial"} opts out of it.
    assert (await registry.get_metadata("product")).synchronizable_mode == "full"
    assert (await registry.get_metadata("ticket")).synchronizable_mode == "partial"

    # A partial model stays synchronizable: only how much it mirrors changes.
    assert (await registry.get_metadata("ticket")).synchronizable is True


async def test_synchronizable_mode_is_none_without_the_action(setup_db: FastEdgy) -> None:
    metadata = await get_service(MetadataModelRegistry).get_metadata("category")

    assert metadata.synchronizable is False
    assert metadata.synchronizable_mode == "none"


async def test_local_placeholder_is_exposed_on_the_field(setup_db: FastEdgy) -> None:
    metadata = await get_service(MetadataModelRegistry).get_metadata("ticket")

    # The client interpolates this while the server-generated value is missing.
    assert metadata.fields["reference"].local_placeholder == "DRAFT-{seq}"
    assert metadata.fields["reference"].readonly is True

    # A field that declares nothing carries no placeholder.
    assert metadata.fields["subject"].local_placeholder is None


async def test_invalid_sync_mode_is_rejected() -> None:
    from fastedgy.api_route_model.actions.sync_action import validate_sync_mode

    with pytest.raises(ValueError, match="Sync mode 'partiel' is not supported"):
        validate_sync_mode("partiel")

    # "none" is derived from the absence of the action, never configured.
    with pytest.raises(ValueError, match="Sync mode 'none' is not supported"):
        validate_sync_mode("none")


async def test_generic_reverse_relations_keep_a_stable_order(setup_db: FastEdgy) -> None:
    # Where a GenericForeignKey installs its reverse side depends on import
    # order, so the generated metadata only stays comparable across runs (and
    # against the committed parity fixture) if those relations are sorted.
    from fastedgy.metadata_model.generator import generate_metadata_model
    from fastedgy.test.models.product import Product

    fields = list((await generate_metadata_model(Product)).fields)
    generic_reverse = [name for name in fields if name in ("annotations", "attachments", "notes")]

    assert generic_reverse == sorted(generic_reverse)
    assert fields.index("name") < fields.index(generic_reverse[0])
