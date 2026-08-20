# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy.core.db.datastructures import Index, UniqueConstraint
from edgy.core.db.fields.factories import FieldFactory, ForeignKeyFieldFactory
from edgy.core.db.fields.types import BaseFieldType

from .field_big_integer import BigIntegerField
from .field_binary import BinaryField
from .field_boolean import BooleanField
from .field_char import CharField
from .field_char_choice import CharChoiceField
from .field_choice import ChoiceEnum, ChoiceField
from .field_composite import CompositeField
from .field_computed import ComputedField
from .field_converter import FieldExportConverter
from .field_date import DateField
from .field_datetime import DateTimeField
from .field_decimal import DecimalField
from .field_duration import DurationField
from .field_email import EmailField
from .field_exclude import ExcludeField
from .field_file import FileField
from .field_float import FloatField
from .field_foreign_key import ForeignKey
from .field_fulltext import (
    SEARCH_WEIGHT_FIELD_MAP,
    FulltextField,
    SearchWeight,
    escape_sql,
    get_pg_language,
    get_searchable_fields,
    recompute_fulltext,
    resolve_search_weight,
)
from .field_generic_foreign_key import (
    GenericForeignKey,
    GenericRelatedField,
    GenericRelation,
    GenericTargets,
    generic_target_name,
    resolve_generic_pair,
    resolve_registry_generic_references,
    validate_generic_reference_payload,
)
from .field_html import HTMLField
from .field_image import ImageField
from .field_integer import IntegerField
from .field_ip_address import IPAddressField
from .field_json import JSONField
from .field_many_to_many import ManyToMany, ManyToManyField
from .field_one_to_one import OneToOne, OneToOneField
from .field_options import FieldOptions
from .field_password import PasswordField
from .field_pg_array import PGArrayField
from .field_phone import PhoneField
from .field_placeholder import PlaceholderField
from .field_point import Point, PointField
from .field_ref_foreign_key import RefForeignKey
from .field_small_integer import SmallIntegerField
from .field_text import TextField
from .field_time import TimeField
from .field_url import URLField
from .field_uuid import UUIDField
from .field_vector import Vector, VectorField

__all__ = [
    "SEARCH_WEIGHT_FIELD_MAP",
    "BaseFieldType",
    "BigIntegerField",
    "BinaryField",
    "BooleanField",
    "CharChoiceField",
    "CharField",
    "ChoiceEnum",
    "ChoiceField",
    "CompositeField",
    "ComputedField",
    "DateField",
    "DateTimeField",
    "DecimalField",
    "DurationField",
    "EmailField",
    "ExcludeField",
    "FieldExportConverter",
    "FieldFactory",
    "FieldOptions",
    "FileField",
    "FloatField",
    "ForeignKey",
    "ForeignKeyFieldFactory",
    "FulltextField",
    "GenericForeignKey",
    "GenericRelatedField",
    "GenericRelation",
    "GenericTargets",
    "HTMLField",
    "IPAddressField",
    "ImageField",
    "Index",
    "IntegerField",
    "JSONField",
    "ManyToMany",
    "ManyToManyField",
    "OneToOne",
    "OneToOneField",
    "PGArrayField",
    "PasswordField",
    "PhoneField",
    "PlaceholderField",
    "Point",
    "PointField",
    "RefForeignKey",
    "SearchWeight",
    "SmallIntegerField",
    "TextField",
    "TimeField",
    "URLField",
    "UUIDField",
    "UniqueConstraint",
    "Vector",
    "VectorField",
    "escape_sql",
    "generic_target_name",
    "get_pg_language",
    "get_searchable_fields",
    "recompute_fulltext",
    "resolve_generic_pair",
    "resolve_registry_generic_references",
    "resolve_search_weight",
    "validate_generic_reference_payload",
]
