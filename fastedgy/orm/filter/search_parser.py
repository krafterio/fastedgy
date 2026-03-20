# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import re


def parse_search_input(raw: str) -> str:
    """
    Parse a Google-style search string into a PostgreSQL tsquery expression.

    Rules:
    - Bare words → prefix match with :*
    - "quoted phrases" → exact phrase match (proximity <->), no :*
    - +word → mandatory (AND)
    - -word → excluded (NOT)
    - Multiple bare words → OR between them
    - +/- terms are combined with AND to the rest

    Examples:
        "courses"           → "courses:*"
        "courses semaine"   → "courses:* | semaine:*"
        "+courses semaine"  → "courses:* & semaine:*"
        "-annulées courses" → "courses:* & !annulées:*"
        '"repas midi"'      → "repas <-> midi"
        'courses +semaine -annulées "repas midi"'
            → "(courses:*) & (semaine:*) & !(annulées:*) & (repas <-> midi)"
    """
    raw = raw.strip()
    if not raw:
        return ""

    tokens = _tokenize(raw)
    if not tokens:
        return ""

    mandatory = []  # AND terms (+ prefix or quoted)
    excluded = []  # NOT terms (- prefix)
    optional = []  # OR terms (bare words)

    for token in tokens:
        if token.type == "mandatory":
            mandatory.append(token.value)
        elif token.type == "excluded":
            excluded.append(token.value)
        elif token.type == "phrase":
            mandatory.append(token.value)
        else:  # bare
            optional.append(token.value)

    parts = []

    # Optional terms combined with OR
    if optional:
        or_expr = " | ".join(optional)
        if len(optional) > 1:
            parts.append(f"({or_expr})")
        else:
            parts.append(or_expr)

    # Mandatory terms combined with AND
    for term in mandatory:
        parts.append(f"({term})")

    # Excluded terms combined with AND NOT
    for term in excluded:
        parts.append(f"!({term})")

    return " & ".join(parts)


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, type: str, value: str):
        self.type = type
        self.value = value


def _tokenize(raw: str) -> list[_Token]:
    """
    Tokenize the search input into typed tokens.
    """
    tokens = []
    i = 0

    while i < len(raw):
        ch = raw[i]

        # Skip whitespace
        if ch.isspace():
            i += 1
            continue

        # Quoted phrase
        if ch == '"':
            end = raw.find('"', i + 1)
            if end == -1:
                end = len(raw)
            phrase = raw[i + 1 : end].strip()
            if phrase:
                words = phrase.split()
                if words:
                    tokens.append(_Token("phrase", " <-> ".join(words)))
            i = end + 1
            continue

        # +word (mandatory)
        if ch == "+" and i + 1 < len(raw) and not raw[i + 1].isspace():
            word, i = _read_word(raw, i + 1)
            if word:
                tokens.append(_Token("mandatory", f"{word}:*"))
            continue

        # -word (excluded)
        if ch == "-" and i + 1 < len(raw) and not raw[i + 1].isspace():
            word, i = _read_word(raw, i + 1)
            if word:
                tokens.append(_Token("excluded", f"{word}:*"))
            continue

        # Bare word
        word, i = _read_word(raw, i)
        if word:
            tokens.append(_Token("bare", f"{word}:*"))

    return tokens


def _read_word(raw: str, start: int) -> tuple[str, int]:
    """Read a word (non-whitespace, non-quote sequence) from position start."""
    end = start
    while end < len(raw) and not raw[end].isspace() and raw[end] != '"':
        end += 1
    return raw[start:end], end


__all__ = [
    "parse_search_input",
]
