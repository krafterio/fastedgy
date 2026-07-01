# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Generic API schema types.

These generic aliases let an endpoint describe its request/response schema by
type annotation alone, without a runtime helper call in annotation position:

    response_model=ModelItem[Product]
    response_model=ModelList[Product]
    item_data: ModelCreate[Product] = Body()
    item_data: ModelUpdate[Product] = Body()

The response is the Edgy model itself — a single schema per model, so there is no
second same-named class for FastAPI >= 0.137 to module-qualify against. The model's
serialization JSON schema is enriched by ``BaseModel.__get_pydantic_json_schema__``
(a foreign key rendered as ``related model | object``, relations exposed as
``list[object]``); ``ModelItem`` passes the ``filter_selected_fields`` dict through
untouched (``SkipValidation`` + ``WrapSerializer``) so an X-Fields selection — which
may include those relations — is not re-serialized (and stripped) through the model.

At type-check time each alias resolves to a plain type so Pyright is happy; at
runtime ``__class_getitem__`` builds the concrete schema.
"""

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import SkipValidation, WrapSerializer

from fastedgy.schemas import create_model
from fastedgy.schemas.base import Pagination


def _serialize_record(value: Any, handler: Any) -> Any:
    """Serialize a CRUD response as-is when it is already a plain ``dict``.

    Every action returns the record through ``filter_selected_fields`` (a dict
    shaped by the X-Fields selection, including exposed relations). Routing that
    dict back through the Edgy model's serializer would drop those relations
    (Edgy excludes them from serialization), so a dict is passed through
    untouched; a model instance still goes through the normal serializer."""
    if isinstance(value, dict):
        return value
    return handler(value)


def _record_type(model: Any) -> Any:
    """A single record: the model (its enriched serialization schema) or a partial
    ``dict`` (an X-Fields selection). ``SkipValidation`` + ``WrapSerializer`` let the
    ``filter_selected_fields`` dict pass through untouched instead of being validated
    (and its exposed relations stripped) back through the Edgy model."""
    return Annotated[model | dict[str, Any], SkipValidation, WrapSerializer(_serialize_record)]


if TYPE_CHECKING:
    type ModelItem[M] = M | dict[str, Any]
    type ModelList[M] = Pagination[M | dict[str, Any]]
    type ModelCreate[M] = M
    type ModelUpdate[M] = M
else:
    from fastedgy.api_route_model.action.generators import (
        generate_input_create_model,
        generate_input_patch_model,
    )

    class ModelItem:
        """A single record: the model (enriched schema) or a partial X-Fields ``dict``."""

        def __class_getitem__(cls, model: Any) -> Any:
            return _record_type(model)

    class ModelList:
        """A paginated list of ``ModelItem[model]``, named ``<Model>-List``."""

        def __class_getitem__(cls, model: Any) -> Any:
            return create_model(
                f"{model.__name__}-List",
                __base__=Pagination[_record_type(model)],
            )

    class ModelCreate:
        """The POST body schema (``<Model>-Create``): writable fields, relations."""

        def __class_getitem__(cls, model: Any) -> Any:
            return generate_input_create_model(model)

    class ModelUpdate:
        """The PATCH body schema (``<Model>-Update``): every field optional."""

        def __class_getitem__(cls, model: Any) -> Any:
            return generate_input_patch_model(model)


__all__ = [
    "ModelItem",
    "ModelList",
    "ModelCreate",
    "ModelUpdate",
]
