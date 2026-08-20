# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Which operators a field type offers.

A type missing from the map answers an empty list, and an empty list means the
column cannot be filtered at all: the query builder refuses every operator, and
the console builds its filter UI from the same map, so nothing is offered there
either. It fails silently — the column simply never appears as filterable.

`CharChoiceField` was in that state. It holds the same enum members as
`ChoiceField` and only differs in storage (a varchar instead of a native
PostgreSQL enum), so it offers the same operators.
"""

from enum import Enum
from typing import Any, cast

from fastedgy.orm import fields
from fastedgy.orm.filter import get_filter_operators


class Status(Enum):
    draft = "draft"
    published = "published"


CHOICE_OPERATORS = ["=", "!=", "in", "not in", "is empty", "is not empty"]


def _operators(field: object) -> list[str]:
    # The field factories are annotated as returning the enum they are given,
    # which is what makes a model attribute type correctly.
    return get_filter_operators(cast(Any, field))


def test_a_choice_field_offers_the_choice_operators() -> None:
    assert _operators(fields.ChoiceField(Status)) == CHOICE_OPERATORS


def test_a_char_choice_field_offers_the_same_ones() -> None:
    assert _operators(fields.CharChoiceField(Status, max_length=16)) == CHOICE_OPERATORS


def test_neither_offers_the_text_operators() -> None:
    """The value comes from a fixed set, so `like` and `contains` mean nothing."""
    for field in (fields.ChoiceField(Status), fields.CharChoiceField(Status, max_length=16)):
        operators = _operators(field)

        assert not [operator for operator in operators if "like" in operator or "contains" in operator]


def test_an_unmapped_field_type_answers_nothing() -> None:
    """The failure mode the two tests above guard against."""

    class Unmapped:
        pass

    assert _operators(Unmapped()) == []
