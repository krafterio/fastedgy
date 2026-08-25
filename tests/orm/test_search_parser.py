# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.orm.filter.search_parser import parse_search_input


@pytest.mark.parametrize(
    "raw",
    [
        "huile d'olive",
        "huile d’olive",
        "lait d’amande",
        "flocons d'avoine",
        "l'eau",
        "d'o",
        "aujourd'hui",
        "s’intéresse",
        '"huile d’olive"',
        "+bio -sucre lait d'amande",
    ],
)
def test_no_quote_survives_the_parser(raw: str) -> None:
    # An apostrophe reaching the output closes the SQL literal the rank
    # expression builds it into, which is where `syntax error at or near
    # "olive"` came from on every French elision.
    parsed = parse_search_input(raw)

    assert "'" not in parsed
    assert "’" not in parsed


def test_elision_splits_into_searchable_words() -> None:
    # to_tsvector('french', "huile d'olive") indexes `huil` and `oliv`, so the
    # query has to carry them apart too.
    assert parse_search_input("huile d'olive") == "(huile:* | d:* | olive:*)"


def test_curly_apostrophe_is_not_a_phrase_delimiter() -> None:
    # A phone keyboard types U+2019. Folded onto `"` it opened a phrase after
    # the elision and swallowed the rest of the query.
    assert parse_search_input("huile d’olive") == parse_search_input("huile d'olive")


def test_quoted_phrase_still_builds_a_proximity_query() -> None:
    assert parse_search_input('"huile d’olive"') == "(huile <-> d <-> olive)"


def test_operators_are_preserved() -> None:
    assert parse_search_input("+bio -sucre lait") == "lait:* & (bio:*) & !(sucre:*)"
