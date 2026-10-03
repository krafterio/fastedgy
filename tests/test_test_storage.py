# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from fastedgy.test import database, fixtures
from fastedgy.test.fixtures import RUN_ID, STORAGE_ROOT, WORKER_ID, remove_abandoned_runs, restore_storage


def test_the_storage_belongs_to_this_launch_and_this_worker() -> None:
    assert os.environ["DATA_PATH"] == STORAGE_ROOT
    assert Path(STORAGE_ROOT).parts[-2:] == (RUN_ID, WORKER_ID)

    if "PYTEST_XDIST_TESTRUNUID" in os.environ:
        assert RUN_ID == os.environ["PYTEST_XDIST_TESTRUNUID"][:12]


def test_a_worker_storage_starts_as_a_copy_of_the_template(tmp_path: Path) -> None:
    template, target = tmp_path / "template", tmp_path / "worker"
    (template / "global").mkdir(parents=True)
    (template / "global" / "seed.txt").write_text("seed", encoding="utf-8")
    (target / "stale").mkdir(parents=True)

    restore_storage(template, str(target))

    assert (target / "global" / "seed.txt").read_text(encoding="utf-8") == "seed"
    assert not (target / "stale").exists()


def test_without_a_template_a_worker_storage_starts_empty(tmp_path: Path) -> None:
    restore_storage(tmp_path / "missing", str(tmp_path / "worker"))

    assert list((tmp_path / "worker").iterdir()) == []


def test_the_template_build_stores_its_files_in_the_storage_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}
    template = tmp_path / "template"
    (template / "stale").mkdir(parents=True)

    def run(args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs["env"])

        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(database.subprocess, "run", run)

    database.ensure_template_database(None, "main", template)

    assert seen["DATA_PATH"] == str(template)
    assert template.is_dir() and list(template.iterdir()) == []


def test_only_the_folders_of_dead_launches_are_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixtures, "STORAGE_RUNS", str(tmp_path))
    old = time.time() - fixtures.ABANDONED_AFTER - 60

    for name in ("dead", "alive", RUN_ID):
        (tmp_path / name).mkdir()

    for name in ("dead", RUN_ID):
        os.utime(tmp_path / name, (old, old))

    remove_abandoned_runs()

    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(["alive", RUN_ID])


def test_an_explicit_database_url_holds_once_the_tests_are_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FASTEDGY_TEST_DATABASE_URL", "postgresql+asyncpg://user:secret@localhost:5432/elsewhere")
    monkeypatch.setenv("FASTEDGY_TEST_ACTIVE", "1")

    assert database.template_database_name() == "elsewhere-test-tpl"
    assert database.worker_database_name("gw1") == "elsewhere-test-2"
