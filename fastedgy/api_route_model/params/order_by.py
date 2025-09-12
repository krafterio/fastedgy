# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Literal, TypeAlias

from edgy import QuerySet, Model
from fastapi.params import Query, Header


class OrderByQuery(Query):
    def __init__(self):
        super().__init__(
            default=None,
            title="Order by",
            description="Order the list of items by field(s) separated by commas (ex. 'created_at:desc,name:asc')",
        )


class OrderByHeader(Header):
    def __init__(self):
        super().__init__(
            default=None,
            title="Order by",
            description="Order the list of items by field(s) separated by commas (ex. 'created_at:desc,name:asc')",
            alias="X-Order-By",
        )


OrderByDirection: TypeAlias = Literal["asc", "desc"]
OrderByTerm: TypeAlias = tuple[str, OrderByDirection]
OrderByList: TypeAlias = list[OrderByTerm]
OrderByInput: TypeAlias = str | OrderByList | None


def inject_order_by(query: QuerySet, order_by: OrderByInput)-> QuerySet:
    order_by_fields = parse_order_by(query.model_class, order_by)

    if order_by_fields:
        formatted_fields = [('-' if direction == 'desc' else '') + field for field, direction in order_by_fields]
        query = query.order_by(*formatted_fields)

    return query



def parse_order_by(model_cls: type[Model], order_by_input: OrderByInput) -> OrderByList:
    """
    Parse order_by into a list of tuples (field_name, direction).

    Format: field1:asc,field2:desc,field3

    Args:
        model_cls: The model class to validate field names against
        order_by_input: The order by string to parse

    Returns:
        List of tuples (field_name, direction)
    """
    if not order_by_input and hasattr(model_cls, 'Meta'):
        order_by_input = getattr(model_cls.Meta, 'default_order_by', None)

    if not order_by_input:
        return []

    if not isinstance(order_by_input, str):
        return order_by_input

    order_terms = []

    for term in order_by_input.split(','):
        term = term.strip()

        if not term:
            continue

        # Parse field and direction
        if ':' in term:
            field, direction = term.split(':', 1)
            direction = direction.lower()

            if direction not in ('asc', 'desc'):
                direction = 'asc'
        else:
            field = term
            direction = 'asc'

        # Validate field exists in model
        if _is_valid_field_path(model_cls, field):
            order_terms.append((field, direction))

    return order_terms


def _is_valid_field_path(model_cls: type[Model], field_path: str) -> bool:
    """
    Check if a field path (including relations) is valid.

    Args:
        model_cls: The model class
        field_path: Field path like 'name' or 'relation.field'

    Returns:
        True if valid, False otherwise
    """
    parts = field_path.split('.')
    current_cls = model_cls

    try:
        for part in parts:
            if part not in current_cls.meta.fields:
                return False

            # Get the field type and check if it's a relation
            field = current_cls.meta.fields.get(part)

            if hasattr(field, 'target'):
                current_cls = field.target

        return True
    except Exception:
        return False


__all__ = [
    "OrderByQuery",
    "OrderByHeader",
    "OrderByDirection",
    "OrderByTerm",
    "OrderByList",
    "OrderByInput",
    "inject_order_by",
    "parse_order_by",
]
