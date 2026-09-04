# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any

from edgy.core.db.fields import PasswordField as _PasswordField

from ...depends.hasher import get_hasher_registry
from .field_options import FieldOptions


class PasswordField(FieldOptions[str], _PasswordField):
    """Password column that refuses to store anything but a hash.

    The field cannot hash on its own. A KDF costs tens to hundreds of
    milliseconds of CPU by design, so it has to run in a worker thread and
    before the request opens its transaction, and every hook reachable from
    inside ``save()`` is already inside the caller's transaction. Hashing
    therefore belongs at the boundary, through ``hash_password_async``, and the
    field is what makes sure nobody forgets: a value none of the registered
    hashers recognises raises instead of being written in clear.

    A field declared with its own ``derive_fn`` hashes at assignment, the Edgy
    way, and is left alone.
    """

    methods_overwritable_by_factory = frozenset(_PasswordField.methods_overwritable_by_factory | {"pre_save_callback"})

    @classmethod
    async def pre_save_callback(
        cls,
        field_obj: Any,
        value: Any,
        original_value: Any,
        is_update: bool,
        original_fn: Any = None,
    ) -> dict[str, Any]:
        if value is None or getattr(field_obj, "derive_fn", None) is not None:
            return {}

        if get_hasher_registry().is_hashed(value):
            return {}

        from ...config import BaseSettings
        from ...dependencies import get_service

        owner = getattr(field_obj, "owner", None)
        model_name = getattr(owner, "__name__", "?")
        message = (
            f"{model_name}.{field_obj.name} was given a value that is not a password hash. "
            f"Hash it with hash_password_async() before saving, or declare the field with a derive_fn."
        )

        if get_service(BaseSettings).strict_password_hash:
            raise ValueError(message)

        # Never store it in clear. Hashing here runs on the caller's
        # transaction, which is exactly what the boundary exists to avoid, so
        # this is a repair and not the normal path: the test suite is what
        # reports it, through the strict mode the toolkit turns on.
        return {field_obj.name: get_hasher_registry().hash(value)}


__all__ = [
    "PasswordField",
]
