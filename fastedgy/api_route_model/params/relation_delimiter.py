# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum

from fastapi.params import Query


class RelationDelimiter(str, Enum):
    """Delimiter for relation values in export."""

    newline = "newline"
    semicolon = "semicolon"
    comma = "comma"

    def get_separator(self) -> str:
        """Return the actual separator character(s)."""
        match self:
            case RelationDelimiter.newline:
                return "\n"
            case RelationDelimiter.semicolon:
                return ";"
            case RelationDelimiter.comma:
                return ","


class RelationDelimiterQuery(Query):
    def __init__(self):
        super().__init__(
            default=RelationDelimiter.newline,
            title="Relation delimiter",
            description="Delimiter for relation values (one2many, many2many) in export cells",
        )


__all__ = [
    "RelationDelimiter",
    "RelationDelimiterQuery",
]
