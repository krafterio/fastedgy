# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import AsyncIterator

import pytest

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.metadata_model.registry import MetadataModelRegistry
from fastedgy.storage.routing import is_global_storage_model, resolve_workspace_for_path


@pytest.fixture
async def gf_article_metadata(setup_db: FastEdgy) -> AsyncIterator[None]:
    from fastedgy.test.models import GfArticle

    registry = get_service(MetadataModelRegistry)
    registry.register_model(GfArticle)

    yield

    registry._lazy_models = [m for m in registry._lazy_models if m is not GfArticle]
    registry._models.pop(GfArticle, None)
    registry._map_names = {k: v for k, v in registry._map_names.items() if v is not GfArticle}


async def test_model_without_workspace_field_is_global(setup_db: FastEdgy) -> None:
    from fastedgy.test.models import Note

    assert is_global_storage_model(Note) is True


async def test_workspaceable_model_is_workspace_scoped(setup_db: FastEdgy) -> None:
    from fastedgy.test.models import GfArticle

    assert is_global_storage_model(GfArticle) is False


async def test_meta_global_storage_forces_global_on_workspaceable_model(
    setup_db: FastEdgy, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastedgy.test.models import GfArticle

    monkeypatch.setattr(GfArticle.Meta, "global_storage", True, raising=False)

    assert is_global_storage_model(GfArticle) is True


async def test_resolve_workspace_for_path_finds_the_owning_workspace(gf_article_metadata) -> None:
    from fastedgy.test.factories import create_workspace
    from fastedgy.test.models import GfArticle

    ws1 = await create_workspace(slug="ws1")
    ws2 = await create_workspace(slug="ws2")
    await GfArticle(title="test_gf_articles/photo-1.jpg", workspace=ws1).save()
    await GfArticle(title="test_gf_articles/photo-2.jpg", workspace=ws2).save()

    owner = await resolve_workspace_for_path("test_gf_articles/photo-2.jpg")

    assert owner is not None
    assert owner.id == ws2.id


async def test_resolve_workspace_for_path_ignores_unknown_segments_and_misses(gf_article_metadata) -> None:
    assert await resolve_workspace_for_path("unknown_folder/x.jpg") is None
    assert await resolve_workspace_for_path("test_gf_articles/missing.jpg") is None
