# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from __future__ import annotations

import re
import unicodedata


# All Unicode quote characters → normalized to ASCII "
_QUOTE_CHARS = re.compile(
    r'["\u00AB\u00BB\u2018\u2019\u201A\u201B\u201C\u201D\u201E\u201F\u2039\u203A\u300C\u300D\u300E\u300F\uFF02]'
)


def _normalize_input(raw: str) -> str:
    """
    Normalize search input:
    - Convert all Unicode quote variants to ASCII "
    - Keep +, -, alphanumeric, spaces, and ASCII "
    - Strip everything else
    """
    # Normalize quotes
    raw = _QUOTE_CHARS.sub('"', raw)

    # Keep only: alphanumeric, spaces, ", +, -, ', -
    result = []
    for ch in raw:
        if ch.isalnum() or ch in (" ", '"', "+", "-", "'", "-"):
            result.append(ch)
        else:
            result.append(" ")

    return "".join(result)


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
    """
    raw = _normalize_input(raw.strip())
    if not raw.strip():
        return ""

    tokens = _tokenize(raw)
    if not tokens:
        return ""

    mandatory = []
    excluded = []
    optional = []

    for token in tokens:
        if token.type == "mandatory":
            mandatory.append(token.value)
        elif token.type == "excluded":
            excluded.append(token.value)
        elif token.type == "phrase":
            mandatory.append(token.value)
        else:
            optional.append(token.value)

    parts = []

    if optional:
        or_expr = " | ".join(optional)
        if len(optional) > 1:
            parts.append(f"({or_expr})")
        else:
            parts.append(or_expr)

    for term in mandatory:
        parts.append(f"({term})")

    for term in excluded:
        parts.append(f"!({term})")

    return " & ".join(parts)


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, type: str, value: str):
        self.type = type
        self.value = value


def _tokenize(raw: str) -> list[_Token]:
    """Tokenize the normalized search input into typed tokens."""
    tokens = []
    i = 0

    while i < len(raw):
        ch = raw[i]

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
                words = [w for w in words if w]
                if words:
                    tokens.append(_Token("phrase", " <-> ".join(words)))
            i = end + 1
            continue

        # +word or + word (mandatory)
        if ch == "+":
            # Skip spaces between + and word
            j = i + 1
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j < len(raw) and raw[j].isalnum():
                word, i = _read_word(raw, j)
                if word:
                    tokens.append(_Token("mandatory", f"{word}:*"))
                continue
            i += 1
            continue

        # -word or - word (excluded)
        if ch == "-":
            j = i + 1
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j < len(raw) and raw[j].isalnum():
                word, i = _read_word(raw, j)
            if word:
                tokens.append(_Token("excluded", f"{word}:*"))
            continue

        # Skip non-alphanumeric
        if not ch.isalnum():
            i += 1
            continue

        # Bare word
        word, i = _read_word(raw, i)
        if word:
            tokens.append(_Token("bare", f"{word}:*"))

    return tokens


def _read_word(raw: str, start: int) -> tuple[str, int]:
    """Read a word (alphanumeric + hyphens/apostrophes) from position start."""
    end = start
    while end < len(raw) and (raw[end].isalnum() or raw[end] in ("'", "-")):
        end += 1
    word = raw[start:end].strip("'-")
    return word, end


__all__ = [
    "parse_search_input",
]
