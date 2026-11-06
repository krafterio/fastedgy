# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.dataflow.exporter import format_value


@pytest.mark.parametrize("text", ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tcell", "\rcell"])
def test_a_text_a_spreadsheet_would_compute_is_exported_as_text(text: str) -> None:
    assert format_value(text) == f"'{text}"


def test_a_number_and_a_plain_text_are_exported_as_they_are() -> None:
    assert format_value(-2) == "-2"
    assert format_value("Plain") == "Plain"
    assert format_value(["=1+1", "ok"]) == "'=1+1\nok"
