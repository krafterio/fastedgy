# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Three-way line-based text merge (à la diff3) for long text fields.

Both writers edit from the same ``base``: hunks touching disjoint line ranges
all survive; overlapping hunks are resolved in favor of the preferred side.
"""

from difflib import SequenceMatcher


def _hunks(base: list[str], other: list[str]) -> list[tuple[int, int, list[str]]]:
    """The edits turning ``base`` into ``other``: (start, end, replacement)."""
    return [
        (i1, i2, other[j1:j2])
        for tag, i1, i2, j1, j2 in SequenceMatcher(a=base, b=other, autojunk=False).get_opcodes()
        if tag != "equal"
    ]


def merge_text_blocks(base: str, server: str, client: str, prefer_client: bool) -> str:
    """Merge two divergent edits of ``base`` line by line.

    Disjoint hunks from both sides all apply; overlapping hunks keep the
    preferred side's version (``prefer_client`` — the last-writer of the
    conflicting operation).
    """
    base_lines = base.splitlines()
    server_hunks = _hunks(base_lines, server.splitlines())
    client_hunks = _hunks(base_lines, client.splitlines())

    def overlaps(a: tuple[int, int, list[str]], b: tuple[int, int, list[str]]) -> bool:
        # Insertions at the same point (i1 == i2) also conflict.
        return a[0] < b[1] and b[0] < a[1] or (a[0], a[1]) == (b[0], b[1])

    kept: list[tuple[int, int, list[str], bool]] = [(*hunk, True) for hunk in client_hunks]

    for hunk in server_hunks:
        conflicting = [other for other in client_hunks if overlaps(hunk, other)]

        if not conflicting:
            kept.append((*hunk, False))
        elif not prefer_client:
            kept = [entry for entry in kept if not overlaps(hunk, (entry[0], entry[1], entry[2]))]
            kept.append((*hunk, False))

    kept.sort(key=lambda entry: (entry[0], entry[1]))

    merged: list[str] = []
    cursor = 0

    for start, end, replacement, _ in kept:
        if start >= cursor:
            merged.extend(base_lines[cursor:start])
            merged.extend(replacement)
            cursor = max(cursor, end)

    merged.extend(base_lines[cursor:])

    return "\n".join(merged)


__all__ = [
    "merge_text_blocks",
]
