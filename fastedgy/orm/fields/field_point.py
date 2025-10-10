# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.fields.factories import FieldFactory
from edgy.core.db.fields.types import BaseFieldType
from sqlalchemy.types import UserDefinedType
from sqlalchemy.dialects.postgresql.base import ischema_names
from typing import Any


class Point(UserDefinedType):
    cache_ok = True

    def __init__(self, srid: int | str = 4326, *args, **kwargs):
        if srid == "Point":
            self.srid = 4326

        self.srid = srid if isinstance(srid, int) else 4326
        super().__init__()

    @property
    def python_type(self):
        return tuple

    def get_col_spec(self, **kw: Any):
        return f"geometry(Point, {self.srid})"

    def bind_processor(self, dialect):
        def process(value):
            return self._coerce(value)

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None

            if isinstance(value, str):
                value = value.strip()

                if value.startswith("0101000020"):
                    from binascii import unhexlify
                    import struct

                    try:
                        data = unhexlify(value)
                        srid = struct.unpack("<I", data[4:8])[0]
                        lon = struct.unpack("<d", data[9:17])[0]
                        lat = struct.unpack("<d", data[17:25])[0]
                        return (lon, lat)
                    except Exception:
                        pass

                if value.upper().startswith("POINT"):
                    coords = value.split("(")[1].split(")")[0].strip()
                    lon, lat = coords.split()
                    return (float(lon), float(lat))

            return value

        return process

    def _coerce(
        self, value: tuple[float, float] | list[float] | str | None
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        if isinstance(value, (tuple, list)):
            if len(value) != 2:
                raise ValueError(
                    "Point must have exactly 2 coordinates (longitude, latitude)"
                )

            lon, lat = float(value[0]), float(value[1])
            return f"SRID={self.srid};POINT({lon} {lat})"

        raise ValueError(f"Invalid type for Point: {type(value)}")

    class comparator_factory(UserDefinedType.Comparator):
        def spatial_distance_to(self, other):
            from sqlalchemy import func

            return func.ST_Distance(self.expr, other)

        def spatial_distance_lt(self, other, distance: float):
            return self.spatial_distance_to(other) < distance

        def spatial_distance_le(self, other, distance: float):
            return self.spatial_distance_to(other) <= distance

        def spatial_distance_gt(self, other, distance: float):
            return self.spatial_distance_to(other) > distance

        def spatial_distance_ge(self, other, distance: float):
            return self.spatial_distance_to(other) >= distance

        def spatial_within_distance(self, other, distance: float):
            from sqlalchemy import func

            return func.ST_DWithin(self.expr, other, distance)

        def spatial_contains(self, other):
            from sqlalchemy import func

            return func.ST_Contains(self.expr, other)

        def spatial_within(self, other):
            from sqlalchemy import func

            return func.ST_Within(self.expr, other)

        def spatial_intersects(self, other):
            from sqlalchemy import func

            return func.ST_Intersects(self.expr, other)

        def spatial_equals(self, other):
            from sqlalchemy import func

            return func.ST_Equals(self.expr, other)

        def spatial_disjoint_from(self, other):
            from sqlalchemy import func

            return func.ST_Disjoint(self.expr, other)

        def spatial_touches(self, other):
            from sqlalchemy import func

            return func.ST_Touches(self.expr, other)

        def spatial_crosses(self, other):
            from sqlalchemy import func

            return func.ST_Crosses(self.expr, other)

        def spatial_overlaps(self, other):
            from sqlalchemy import func

            return func.ST_Overlaps(self.expr, other)


ischema_names["geometry"] = Point


class PointField(FieldFactory, tuple):
    field_type = tuple[float, float]

    def __new__(
        cls,
        *,
        srid: int = 4326,
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
        return Point(srid=kwargs.get("srid", 4326))

    @classmethod
    def validate(cls, kwargs: dict[str, Any]) -> None:
        srid = kwargs.get("srid", 4326)
        if not isinstance(srid, int) or srid <= 0:
            raise ValueError("srid must be a positive integer")


__all__ = [
    "Point",
    "PointField",
]
