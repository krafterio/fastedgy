# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model.action.base import (
    ApiRouteActionRegistry,
    BaseApiRouteAction,
)
from fastedgy.api_route_model.action.generators import (
    clean_empty_strings,
    generate_input_create_model,
    generate_input_patch_model,
    optional_field_type,
)
from fastedgy.api_route_model.action.relations import (
    get_related_model,
    is_exposed_relation_field,
    is_foreign_key_field,
    is_relation_field,
    process_foreign_key_fields,
    process_relational_fields,
)

__all__ = [
    # Base
    "BaseApiRouteAction",
    "ApiRouteActionRegistry",
    # Generators
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
    # Relations
    "is_relation_field",
    "is_exposed_relation_field",
    "is_foreign_key_field",
    "get_related_model",
    "process_relational_fields",
    "process_foreign_key_fields",
]
