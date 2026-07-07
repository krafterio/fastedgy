# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

import pytest

from fastedgy.logger import LogFormat, LogLevel, LogOutput, setup_logging


@pytest.fixture(autouse=True)
def restore_logging_state():
    root = logging.getLogger()
    previous_level = root.level
    previous_handlers = root.handlers[:]
    yield
    root.handlers[:] = previous_handlers
    root.setLevel(previous_level)


def _read_streams(capsys) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


def test_explicit_child_logger_level_cannot_bypass_the_configured_floor(capsys):
    setup_logging(level=LogLevel.ERROR, output=LogOutput.CONSOLE, format=LogFormat.JSON)

    library_logger = logging.getLogger("test_noisy_library")
    library_logger.setLevel(logging.WARNING)
    library_logger.warning("compat fixup, should stay below the error floor")

    assert "compat fixup" not in _read_streams(capsys)


def test_error_records_still_reach_the_output_at_error_level(capsys):
    setup_logging(level=LogLevel.ERROR, output=LogOutput.CONSOLE, format=LogFormat.JSON)

    logging.getLogger("test_noisy_library").error("a real failure")

    assert "a real failure" in _read_streams(capsys)


def test_warnings_are_visible_at_warning_level(capsys):
    setup_logging(level=LogLevel.WARNING, output=LogOutput.CONSOLE, format=LogFormat.JSON)

    library_logger = logging.getLogger("test_noisy_library")
    library_logger.setLevel(logging.WARNING)
    library_logger.warning("visible at the configured level")

    assert "visible at the configured level" in _read_streams(capsys)
