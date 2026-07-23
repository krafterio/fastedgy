# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.text_merge import merge_text_blocks

BASE = "line one\nline two\nline three\nline four"


def test_disjoint_edits_both_survive() -> None:
    server = BASE.replace("line one", "SERVER one")
    client = BASE.replace("line four", "CLIENT four")

    merged = merge_text_blocks(BASE, server, client, prefer_client=True)

    assert merged == "SERVER one\nline two\nline three\nCLIENT four"
    assert merged == merge_text_blocks(BASE, server, client, prefer_client=False)


def test_overlapping_edit_keeps_the_preferred_side() -> None:
    server = BASE.replace("line two", "SERVER two")
    client = BASE.replace("line two", "CLIENT two")

    assert "CLIENT two" in merge_text_blocks(BASE, server, client, prefer_client=True)
    assert "SERVER two" in merge_text_blocks(BASE, server, client, prefer_client=False)


def test_insertions_and_deletions_merge() -> None:
    server = "line zero\n" + BASE
    client = BASE.replace("line three\n", "")

    merged = merge_text_blocks(BASE, server, client, prefer_client=True)

    assert merged == "line zero\nline one\nline two\nline four"
