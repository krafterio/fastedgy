# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Literal, TypeAlias

from fastedgy.orm.query import (
    Q,
    not_,
)
from fastedgy.orm.fields import (
    BaseFieldType,
    ForeignKeyFieldFactory,
    FieldFactory,
    IntegerField,
    BooleanField,
    CharField,
    TextField,
    ChoiceField,
    DateField,
    DateTimeField,
    DurationField,
    DecimalField,
    EmailField,
    FileField,
    FloatField,
    ForeignKey,
    RefForeignKey,
    ManyToMany,
    IPAddressField,
    JSONField,
    BinaryField,
    OneToOneField,
    TimeField,
    UUIDField,
    VectorField,
    PointField,
)

from sqlalchemy import null


FilterOperator: TypeAlias = Literal[
    # Generic operators
    "=",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "between",
    "like",
    "ilike",
    "not like",
    "not ilike",
    "starts with",
    "ends with",
    "not starts with",
    "not ends with",
    "contains",
    "icontains",
    "not contains",
    "not icontains",
    "match",
    "in",
    "not in",
    "is true",
    "is false",
    "is empty",
    "is not empty",
    # Distance operators
    "l1 distance",
    "l1 distance <",
    "l1 distance <=",
    "l1 distance >",
    "l1 distance >=",
    "l2 distance",
    "l2 distance <",
    "l2 distance <=",
    "l2 distance >",
    "l2 distance >=",
    "cosine distance",
    "cosine distance <",
    "cosine distance <=",
    "cosine distance >",
    "cosine distance >=",
    "inner product",
    "inner product <",
    "inner product <=",
    "inner product >",
    "inner product >=",
    # Spatial operators
    "spatial distance",
    "spatial distance <",
    "spatial distance <=",
    "spatial distance >",
    "spatial distance >=",
    "spatial within distance",
    "spatial contains",
    "spatial within",
    "spatial intersects",
    "spatial equals",
    "spatial disjoint",
    "spatial touches",
    "spatial crosses",
    "spatial overlaps",
]


FilterConditionType: TypeAlias = Literal[
    "&",
    "|",
]


FILTER_OPERATORS_SQL = {
    # Generic operators
    "=": lambda c, v: c.__eq__(v),
    "!=": lambda c, v: c.__ne__(v),
    "<": lambda c, v: c.__lt__(v),
    "<=": lambda c, v: c.__le__(v),
    ">": lambda c, v: c.__gt__(v),
    ">=": lambda c, v: c.__ge__(v),
    "between": lambda c, v: c.between(*v),
    "like": lambda c, v: c.like(v),
    "ilike": lambda c, v: c.ilike(v),
    "not like": lambda c, v: c.notlike(v),
    "not ilike": lambda c, v: c.notilike(v),
    "starts with": lambda c, v: c.startswith(v),
    "ends with": lambda c, v: c.endswith(v),
    "not starts with": lambda c, v: not_(c.startswith(v)),
    "not ends with": lambda c, v: not_(c.endswith(v)),
    "contains": lambda c, v: c.contains(v),
    "icontains": lambda c, v: c.icontains(v),
    "not contains": lambda c, v: not_(c.contains(v)),
    "not icontains": lambda c, v: not_(c.icontains(v)),
    "match": lambda c, v: c.match(v),
    "in": lambda c, v: c.in_(v),
    "not in": lambda c, v: c.not_in(v),
    "is true": lambda c, v=None: c.is_(True),
    "is false": lambda c, v=None: c.is_(False),
    "is empty": lambda c, v=None: c.is_(null()),
    "is not empty": lambda c, v=None: c.is_not(null()),
    # Distance operators
    "l1 distance": lambda c, v=None: c.l1_distance(v),
    "l1 distance <": lambda c, v=None: c.l1_distance_lt(v),
    "l1 distance <=": lambda c, v=None: c.l1_distance_le(v),
    "l1 distance >": lambda c, v=None: c.l1_distance_gt(v),
    "l1 distance >=": lambda c, v=None: c.l1_distance_ge(v),
    "l2 distance": lambda c, v=None: c.l2_distance(v),
    "l2 distance <": lambda c, v=None: c.l2_distance_lt(v),
    "l2 distance <=": lambda c, v=None: c.l2_distance_le(v),
    "l2 distance >": lambda c, v=None: c.l2_distance_gt(v),
    "l2 distance >=": lambda c, v=None: c.l2_distance_ge(v),
    "cosine distance": lambda c, v=None: c.cosine_distance(v),
    "cosine distance <": lambda c, v=None: c.cosine_distance_lt(v),
    "cosine distance <=": lambda c, v=None: c.cosine_distance_le(v),
    "cosine distance >": lambda c, v=None: c.cosine_distance_gt(v),
    "cosine distance >=": lambda c, v=None: c.cosine_distance_ge(v),
    "inner product": lambda c, v=None: c.inner_product(v),
    "inner product <": lambda c, v=None: c.inner_product_lt(v),
    "inner product <=": lambda c, v=None: c.inner_product_le(v),
    "inner product >": lambda c, v=None: c.inner_product_gt(v),
    "inner product >=": lambda c, v=None: c.inner_product_ge(v),
    # Spatial operators
    "spatial distance": lambda c, v=None: c.spatial_distance_to(v),
    "spatial distance <": lambda c, v=None: c.spatial_distance_lt(v),
    "spatial distance <=": lambda c, v=None: c.spatial_distance_le(v),
    "spatial distance >": lambda c, v=None: c.spatial_distance_gt(v),
    "spatial distance >=": lambda c, v=None: c.spatial_distance_ge(v),
    "spatial within distance": lambda c, v=None: c.spatial_within_distance(v),
    "spatial contains": lambda c, v=None: c.spatial_contains(v),
    "spatial within": lambda c, v=None: c.spatial_within(v),
    "spatial intersects": lambda c, v=None: c.spatial_intersects(v),
    "spatial equals": lambda c, v=None: c.spatial_equals(v),
    "spatial disjoint": lambda c, v=None: c.spatial_disjoint_from(v),
    "spatial touches": lambda c, v=None: c.spatial_touches(v),
    "spatial crosses": lambda c, v=None: c.spatial_crosses(v),
    "spatial overlaps": lambda c, v=None: c.spatial_overlaps(v),
}


FILTER_DICT_OPERATORS_SQL = {
    # Generic operators
    "=": lambda qs, f, v: Q({f"{f.replace('.', '__')}": v}),
    "!=": lambda qs, f, v: qs.not_(Q({f"{f.replace('.', '__')}": v})),
    "<": lambda qs, f, v: Q({f"{f.replace('.', '__')}__lt": v}),
    "<=": lambda qs, f, v: Q({f"{f.replace('.', '__')}__le": v}),
    ">": lambda qs, f, v: Q({f"{f.replace('.', '__')}__gt": v}),
    ">=": lambda qs, f, v: Q({f"{f.replace('.', '__')}__ge": v}),
    "between": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__ge": v[0], f"{f.replace('.', '__')}__le": v[1]}
    ),
    "like": lambda qs, f, v: Q({f"{f.replace('.', '__')}__like": v}),
    "ilike": lambda qs, f, v: Q({f"{f.replace('.', '__')}__ilike": v}),
    "not like": lambda qs, f, v: qs.not_(Q({f"{f.replace('.', '__')}__like": v})),
    "not ilike": lambda qs, f, v: qs.not_(Q({f"{f.replace('.', '__')}__ilike": v})),
    "starts with": lambda qs, f, v: Q({f"{f.replace('.', '__')}__startswith": v}),
    "ends with": lambda qs, f, v: Q({f"{f.replace('.', '__')}__endswith": v}),
    "not starts with": lambda qs, f, v: qs.not_(
        Q({f"{f.replace('.', '__')}__startswith": v})
    ),
    "not ends with": lambda qs, f, v: qs.not_(
        Q({f"{f.replace('.', '__')}__endswith": v})
    ),
    "contains": lambda qs, f, v: Q({f"{f.replace('.', '__')}__contains": v}),
    "icontains": lambda qs, f, v: Q({f"{f.replace('.', '__')}__icontains": v}),
    "not contains": lambda qs, f, v: qs.not_(
        Q({f"{f.replace('.', '__')}__contains": v})
    ),
    "not icontains": lambda qs, f, v: qs.not_(
        Q({f"{f.replace('.', '__')}__icontains": v})
    ),
    "match": lambda qs, f, v: Q({f"{f.replace('.', '__')}__match": v}),
    "in": lambda qs, f, v: Q({f"{f.replace('.', '__')}__in": v}),
    "not in": lambda qs, f, v: qs.not_(Q({f"{f.replace('.', '__')}__in": v})),
    "is true": lambda qs, f, v: Q({f"{f.replace('.', '__')}__is": True}),
    "is false": lambda qs, f, v: Q({f"{f.replace('.', '__')}__is": False}),
    "is empty": lambda qs, f, v: Q({f"{f.replace('.', '__')}__is": None}),
    "is not empty": lambda qs, f, v: qs.not_(Q({f"{f.replace('.', '__')}__is": None})),
    # Distance operators
    "l1 distance": lambda qs, f, v: Q({f"{f.replace('.', '__')}__l1_distance": v}),
    "l1 distance <": lambda qs, f, v: Q({f"{f.replace('.', '__')}__l1_distance_lt": v}),
    "l1 distance <=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__l1_distance_le": v}
    ),
    "l1 distance >": lambda qs, f, v: Q({f"{f.replace('.', '__')}__l1_distance_gt": v}),
    "l1 distance >=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__l1_distance_ge": v}
    ),
    "l2 distance": lambda qs, f, v: Q({f"{f.replace('.', '__')}__l2_distance": v}),
    "l2 distance <": lambda qs, f, v: Q({f"{f.replace('.', '__')}__l2_distance_lt": v}),
    "l2 distance <=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__l2_distance_le": v}
    ),
    "l2 distance >": lambda qs, f, v: Q({f"{f.replace('.', '__')}__l2_distance_gt": v}),
    "l2 distance >=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__l2_distance_ge": v}
    ),
    "cosine distance": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__cosine_distance": v}
    ),
    "cosine distance <": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__cosine_distance_lt": v}
    ),
    "cosine distance <=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__cosine_distance_le": v}
    ),
    "cosine distance >": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__cosine_distance_gt": v}
    ),
    "cosine distance >=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__cosine_distance_ge": v}
    ),
    "inner product": lambda qs, f, v: Q({f"{f.replace('.', '__')}__inner_product": v}),
    "inner product <": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__inner_product_lt": v}
    ),
    "inner product <=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__inner_product_le": v}
    ),
    "inner product >": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__inner_product_gt": v}
    ),
    "inner product >=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__inner_product_ge": v}
    ),
    # Spatial operators
    "spatial distance": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_distance_to": v}
    ),
    "spatial distance <": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_distance_lt": v}
    ),
    "spatial distance <=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_distance_le": v}
    ),
    "spatial distance >": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_distance_gt": v}
    ),
    "spatial distance >=": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_distance_ge": v}
    ),
    "spatial within distance": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_within_distance": v}
    ),
    "spatial contains": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_contains": v}
    ),
    "spatial within": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_within": v}
    ),
    "spatial intersects": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_intersects": v}
    ),
    "spatial equals": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_equals": v}
    ),
    "spatial disjoint": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_disjoint_from": v}
    ),
    "spatial touches": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_touches": v}
    ),
    "spatial crosses": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_crosses": v}
    ),
    "spatial overlaps": lambda qs, f, v: Q(
        {f"{f.replace('.', '__')}__spatial_overlaps": v}
    ),
}


FILTER_OPERATORS_SQL_UNPACK = {
    # Generic operators
    "between": 2,
    # Distance operators
    "l1 distance <": 2,
    "l1 distance <=": 2,
    "l1 distance >": 2,
    "l1 distance >=": 2,
    "l2 distance <": 2,
    "l2 distance <=": 2,
    "l2 distance >": 2,
    "l2 distance >=": 2,
    "cosine distance <": 2,
    "cosine distance <=": 2,
    "cosine distance >": 2,
    "cosine distance >=": 2,
    "inner product <": 2,
    "inner product <=": 2,
    "inner product >": 2,
    "inner product >=": 2,
    # Spatial operators
    "spatial distance <": 2,
    "spatial distance <=": 2,
    "spatial distance >": 2,
    "spatial distance >=": 2,
    "spatial within distance": 2,
}


FILTER_OPERATORS_FIELD_MAP = {
    IntegerField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    BooleanField: [
        "is true",
        "is false",
    ],
    CharField: [
        "=",
        "!=",
        "like",
        "ilike",
        "not like",
        "not ilike",
        "starts with",
        "ends with",
        "not starts with",
        "not ends with",
        "contains",
        "icontains",
        "not contains",
        "not icontains",
        "match",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    EmailField: [
        "=",
        "!=",
        "like",
        "ilike",
        "not like",
        "not ilike",
        "starts with",
        "ends with",
        "not starts with",
        "not ends with",
        "contains",
        "icontains",
        "not contains",
        "not icontains",
        "match",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    TextField: [
        "=",
        "!=",
        "like",
        "ilike",
        "not like",
        "not ilike",
        "starts with",
        "ends with",
        "not starts with",
        "not ends with",
        "contains",
        "icontains",
        "not contains",
        "not icontains",
        "match",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    ChoiceField: [
        "=",
        "!=",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    DateField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "is empty",
        "is not empty",
    ],
    DateTimeField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "is empty",
        "is not empty",
    ],
    DurationField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    DecimalField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    FileField: [
        "is empty",
        "is not empty",
    ],
    FloatField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    ForeignKey: [
        "=",
        "!=",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    RefForeignKey: [
        "=",
        "!=",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    ManyToMany: [
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    IPAddressField: [
        "=",
        "!=",
        "like",
        "ilike",
        "not like",
        "not ilike",
        "starts with",
        "ends with",
        "not starts with",
        "not ends with",
        "contains",
        "icontains",
        "not contains",
        "not icontains",
        "match",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    JSONField: [
        "is empty",
        "is not empty",
    ],
    BinaryField: [
        "is empty",
        "is not empty",
    ],
    OneToOneField: [  # OneToOne extends OneToOneField
        "=",
        "!=",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    TimeField: [
        "=",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "between",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    UUIDField: [
        "=",
        "!=",
        "like",
        "ilike",
        "not like",
        "not ilike",
        "starts with",
        "ends with",
        "not starts with",
        "not ends with",
        "contains",
        "icontains",
        "not contains",
        "not icontains",
        "match",
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
    VectorField: [
        "l1 distance",
        "l1 distance <",
        "l1 distance <=",
        "l1 distance >",
        "l1 distance >=",
        "l2 distance",
        "l2 distance <",
        "l2 distance <=",
        "l2 distance >",
        "l2 distance >=",
        "cosine distance",
        "cosine distance <",
        "cosine distance <=",
        "cosine distance >",
        "cosine distance >=",
        "inner product",
        "inner product <",
        "inner product <=",
        "inner product >",
        "inner product >=",
    ],
    PointField: [
        "spatial distance",
        "spatial distance <",
        "spatial distance <=",
        "spatial distance >",
        "spatial distance >=",
        "spatial within distance",
        "spatial contains",
        "spatial within",
        "spatial intersects",
        "spatial equals",
        "spatial disjoint",
        "spatial touches",
        "spatial crosses",
        "spatial overlaps",
        "is empty",
        "is not empty",
    ],
    "OneToMany": [
        "in",
        "not in",
        "is empty",
        "is not empty",
    ],
}


FILTER_FIELD_TYPE_NAME_MAP = {
    "DateTimeField": "datetime",
    "ForeignKey": "many2one",
    "JSONField": "json",
    "IPAddressField": "ipaddress",
    "OneToOne": "one2one",
    "OneToOneField": "one2one",
    "RefForeignKey": "many2one_ref",
    "UUIDField": "uuid",
    "ManyToMany": "many2many",
    "ManyToManyField": "many2many",
    "OneToMany": "one2many",
}


def get_filter_operators(
    field_info: BaseFieldType | FieldFactory | ForeignKeyFieldFactory | str,
) -> list[str]:
    if isinstance(field_info, str):
        return FILTER_OPERATORS_FIELD_MAP.get(field_info, [])

    field_type = type(field_info)

    if field_type in FILTER_OPERATORS_FIELD_MAP:
        return FILTER_OPERATORS_FIELD_MAP[field_type]

    if field_info in FILTER_OPERATORS_FIELD_MAP:
        return FILTER_OPERATORS_FIELD_MAP[field_info]

    for map_field_type, allowed_operators in FILTER_OPERATORS_FIELD_MAP.items():
        if isinstance(field_info, str) and field_info == map_field_type:
            return allowed_operators

        if not isinstance(map_field_type, str) and isinstance(
            field_info, map_field_type
        ):
            return allowed_operators

    return []


__all__ = [
    "FilterOperator",
    "FilterConditionType",
    "FILTER_OPERATORS_SQL",
    "FILTER_DICT_OPERATORS_SQL",
    "FILTER_OPERATORS_SQL_UNPACK",
    "FILTER_OPERATORS_FIELD_MAP",
    "FILTER_FIELD_TYPE_NAME_MAP",
    "get_filter_operators",
]
