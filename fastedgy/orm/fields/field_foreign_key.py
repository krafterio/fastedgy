# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Sequence
from functools import cache
from typing import Any

import sqlalchemy
from edgy.core.db.fields import ForeignKey as _ForeignKey

from .field_options import FieldOptions


class ForeignKey(FieldOptions[Any], _ForeignKey):
    """Edgy foreign key, plus ``use_alter=True`` for the key that closes a cycle
    of tables referencing one another (``households.primary_address`` while
    ``spots.workspace`` points back): SQLAlchemy then creates that constraint
    after both tables and can order the metadata, instead of warning that it
    cannot sort them.

    ``input_optional=True`` keeps a non-nullable key required in the database
    while the generated API routes accept a creation without it: the body may
    leave it out or send null, the metadata no longer marks it required, and a
    ``pre_save`` signal fills it before the insert. An update still refuses null.

    The option lives on the field class rather than on a factory override: Edgy
    binds a factory override to the field it first built, while each model works
    on a copy of that field, and only the copy knows its model.
    """

    @staticmethod
    @cache
    def _get_field_cls(factory_cls: Any) -> Any:
        field_cls = FieldOptions._get_field_cls(factory_cls)

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            if kwargs.get("input_optional"):
                kwargs.setdefault("default", None)

            field_cls.__init__(self, *args, **kwargs)

        def get_global_constraints(
            self: Any, *args: Any, **kwargs: Any
        ) -> Sequence[sqlalchemy.Constraint | sqlalchemy.Index]:
            constraints = field_cls.get_global_constraints(self, *args, **kwargs)

            if getattr(self, "use_alter", False):
                for constraint in constraints:
                    if isinstance(constraint, sqlalchemy.ForeignKeyConstraint):
                        constraint.use_alter = True

            return constraints

        return type(
            field_cls.__name__,
            (field_cls,),
            {"__init__": __init__, "get_global_constraints": get_global_constraints},
        )


__all__ = [
    "ForeignKey",
]
