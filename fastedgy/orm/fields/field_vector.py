# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields.factories import FieldFactory
from edgy.core.db.fields.types import BaseFieldType
from sqlalchemy.types import UserDefinedType
from sqlalchemy.dialects.postgresql.base import ischema_names
from typing import Any, Iterable, Sequence


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int | None = None):
        self.dimensions = dimensions
        super().__init__()

    @property
    def python_type(self):
        return list

    def get_col_spec(self, **kw: Any):
        return f"VECTOR({self.dimensions})" if self.dimensions else "VECTOR"

    def bind_processor(self, dialect):
        def process(value):
            return self._coerce(value)

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None

            if isinstance(value, str):
                s = value.strip()

                if s.startswith("[") and s.endswith("]"):
                    inner = s[1:-1].strip()

                    if not inner:
                        return []

                    return [float(x.strip()) for x in inner.split(",")]
            return value

        return process

    def _coerce(
        self, value: Iterable[float] | Sequence[float] | str | None
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        if self.dimensions is not None and hasattr(value, "__len__"):
            if len(value) != self.dimensions:  # type: ignore[arg-type]
                raise ValueError(f"Vector length must be {self.dimensions}")

        return "[" + ",".join(str(float(x)) for x in value) + "]"  # type: ignore[arg-type]

    class comparator_factory(UserDefinedType.Comparator):
        def l1_distance(self, other: Iterable[float]):
            return self.expr.op("<+>")(other)

        def l1_distance_lt(self, other: Iterable[float], thresh: float):
            return self.l1_distance(other) < thresh

        def l1_distance_le(self, other: Iterable[float], thresh: float):
            return self.l1_distance(other) <= thresh

        def l1_distance_gt(self, other: Iterable[float], thresh: float):
            return self.l1_distance(other) > thresh

        def l1_distance_ge(self, other: Iterable[float], thresh: float):
            return self.l1_distance(other) >= thresh

        def l2_distance(self, other: Iterable[float]):
            return self.expr.op("<->")(other)

        def l2_distance_lt(self, other: Iterable[float], thresh: float):
            return self.l2_distance(other) < thresh

        def l2_distance_le(self, other: Iterable[float], thresh: float):
            return self.l2_distance(other) <= thresh

        def l2_distance_gt(self, other: Iterable[float], thresh: float):
            return self.l2_distance(other) > thresh

        def l2_distance_ge(self, other: Iterable[float], thresh: float):
            return self.l2_distance(other) >= thresh

        def cosine_distance(self, other: Iterable[float]):
            return self.expr.op("<=>")(other)

        def cosine_distance_lt(self, other: Iterable[float], thresh: float):
            return self.cosine_distance(other) < thresh

        def cosine_distance_le(self, other: Iterable[float], thresh: float):
            return self.cosine_distance(other) <= thresh

        def cosine_distance_gt(self, other: Iterable[float], thresh: float):
            return self.cosine_distance(other) > thresh

        def cosine_distance_ge(self, other: Iterable[float], thresh: float):
            return self.cosine_distance(other) >= thresh

        def inner_product(self, other: Iterable[float]):
            return self.expr.op("<#>")(other)

        def inner_product_lt(self, other: Iterable[float], thresh: float):
            return self.inner_product(other) < thresh

        def inner_product_le(self, other: Iterable[float], thresh: float):
            return self.inner_product(other) <= thresh

        def inner_product_gt(self, other: Iterable[float], thresh: float):
            return self.inner_product(other) > thresh

        def inner_product_ge(self, other: Iterable[float], thresh: float):
            return self.inner_product(other) >= thresh


ischema_names["vector"] = Vector


class VectorField(FieldFactory, list):
    field_type = list[float]

    def __new__(
        cls,
        *,
        dimensions: int | None = None,
        **kwargs: Any,
    ) -> BaseFieldType:
        kwargs = {
            **kwargs,
            **{
                k: v
                for k, v in locals().items()
                if k not in ["cls", "__class__", "kwargs"]
            },
        }
        return super().__new__(cls, **kwargs)

    @classmethod
    def get_column_type(cls, kwargs: dict[str, Any]) -> Any:
        return Vector(dimensions=kwargs.get("dimensions"))

    @classmethod
    def validate(cls, kwargs: dict[str, Any]) -> None:
        dimensions = kwargs.get("dimensions")
        if dimensions is not None and (
            not isinstance(dimensions, int) or dimensions <= 0
        ):
            raise ValueError("dimensions must be a positive integer")


__all__ = [
    "Vector",
    "VectorField",
]
