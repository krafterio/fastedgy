# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Dynamic values in a filter, in the format of the domains of Kastor.

A string between backticks is an expression, evaluated each time the filter is
validated rather than when it was written: a filter saved as
``["created_at", ">=", "`today(-30)`"]`` keeps the last thirty days whatever
the day it is read. ``today(offset)`` is the ISO day, in UTC, moved by
``offset`` days, ``now()`` the ISO instant.

Only a small part of the language is evaluated: numbers, strings, ``true``,
``false``, ``null``, lists, a unary ``-`` or ``+``, ``+ - * / %``, and calls to
the functions below. The text is read by ``ast`` and every other node is
refused, so a stored filter never runs code.
"""

import ast
import operator
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastedgy.orm.filter.types import InvalidFilterError

MAX_LENGTH = 200


def today(offset: Any = 0) -> str:
    if isinstance(offset, bool) or not isinstance(offset, int | float):
        raise TypeError("today() takes a number of days")

    return (datetime.now(UTC) + timedelta(days=offset)).date().isoformat()


def now() -> str:
    return datetime.now(UTC).isoformat()


FUNCTIONS: dict[str, Callable[..., Any]] = {"today": today, "now": now}

CONSTANTS: dict[str, Any] = {"true": True, "false": False, "null": None}

BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def is_expression(value: Any) -> bool:
    return isinstance(value, str) and len(value) > 2 and value.startswith("`") and value.endswith("`")


def _evaluate(node: ast.AST) -> Any:
    match node:
        case ast.Constant(value=value) if isinstance(value, int | float | str) and not isinstance(value, bool):
            return value
        case ast.Name(id=name) if name in CONSTANTS:
            return CONSTANTS[name]
        case ast.List(elts=elements):
            return [_evaluate(element) for element in elements]
        case ast.UnaryOp(op=op, operand=operand) if type(op) in UNARY:
            return UNARY[type(op)](_evaluate(operand))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in BINARY:
            return BINARY[type(op)](_evaluate(left), _evaluate(right))
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in FUNCTIONS:
            return FUNCTIONS[name](*(_evaluate(arg) for arg in args))

    raise ValueError(f"{ast.dump(node)} is not allowed in an expression")


def evaluate(expression: str) -> Any:
    """The value of an expression, written with or without its backticks."""
    text = (expression[1:-1] if is_expression(expression) else expression).strip()

    if len(text) > MAX_LENGTH:
        raise InvalidFilterError(f"An expression holds {MAX_LENGTH} characters at most")

    try:
        return _evaluate(ast.parse(text, mode="eval").body)
    except (SyntaxError, ArithmeticError, TypeError, ValueError) as error:
        raise InvalidFilterError(f"Invalid expression {expression!r}: {error}") from error


def resolve(value: Any) -> Any:
    """A filter value with its expressions evaluated, inside a list too."""
    if is_expression(value):
        return evaluate(value)

    if isinstance(value, list | tuple):
        return [resolve(one) for one in value]

    return value


__all__ = ["FUNCTIONS", "evaluate", "is_expression", "now", "resolve", "today"]
