# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pathlib import Path

import uvicorn
from uvicorn.supervisors.watchfilesreload import FileFilter

from fastedgy.cli.serve import _reload_options


def test_the_reloader_follows_the_translations_and_leaves_the_tests_out(tmp_path: Path) -> None:
    for folder in ("tests", "translations", "models"):
        (tmp_path / folder).mkdir()

    config = uvicorn.Config("main:app", reload=True, **_reload_options(str(tmp_path)))
    reloads = FileFilter(config)

    assert reloads(tmp_path / "translations" / "fr.po")
    assert reloads(tmp_path / "models" / "flow.py")
    assert not reloads(tmp_path / "tests" / "test_flow.py")
    assert _reload_options(str(tmp_path / "elsewhere"))["reload_excludes"] is None
