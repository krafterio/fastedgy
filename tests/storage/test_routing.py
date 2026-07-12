# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.app import FastEdgy
from fastedgy.storage.routing import is_global_storage_model


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
