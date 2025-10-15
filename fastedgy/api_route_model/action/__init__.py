# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model.action.base import (
    BaseApiRouteAction,
    ApiRouteActionRegistry,
)

from fastedgy.api_route_model.action.generators import (
    generate_output_model,
    generate_input_create_model,
    generate_input_patch_model,
    optional_field_type,
    clean_empty_strings,
)

from fastedgy.api_route_model.action.relations import (
    is_relation_field,
    get_related_model,
    process_relational_fields,
)


__all__ = [
    # Base
    "BaseApiRouteAction",
    "ApiRouteActionRegistry",
    # Generators
    "generate_output_model",
    "generate_input_create_model",
    "generate_input_patch_model",
    "optional_field_type",
    "clean_empty_strings",
    # Relations
    "is_relation_field",
    "get_related_model",
    "process_relational_fields",
]
