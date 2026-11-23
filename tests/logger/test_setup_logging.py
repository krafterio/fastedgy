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


@pytest.fixture
def pyvips_logger():
    library_logger = logging.getLogger("pyvips")
    previous_filters = library_logger.filters[:]
    yield library_logger
    library_logger.filters[:] = previous_filters


def test_the_steps_libvips_reports_at_info_stay_out_of_an_info_output(capsys, pyvips_logger):
    setup_logging(level=LogLevel.INFO, output=LogOutput.CONSOLE, format=LogFormat.JSON)

    pyvips_logger.info("VIPS: thumbnailing 1250341 bytes of data")
    pyvips_logger.warning("VIPS: a real warning")

    output = _read_streams(capsys)
    assert "thumbnailing" not in output
    assert "a real warning" in output


def test_the_steps_libvips_reports_show_at_debug(capsys, pyvips_logger):
    setup_logging(level=LogLevel.DEBUG, output=LogOutput.CONSOLE, format=LogFormat.TEXT)
    setup_logging(level=LogLevel.DEBUG, output=LogOutput.CONSOLE, format=LogFormat.TEXT)

    pyvips_logger.info("VIPS: thumbnailing 1250341 bytes of data")

    output = _read_streams(capsys)
    assert "thumbnailing" in output and "DEBUG" in output
    assert len([f for f in pyvips_logger.filters if type(f).__name__ == "InfoAsDebugFilter"]) == 1
