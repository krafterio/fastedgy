# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from fastapi import HTTPException

from fastedgy.dependencies import get_service, register_service


class ModelAction(Enum):
    read = "read"
    create = "create"
    update = "update"
    delete = "delete"


class AccessDeniedError(HTTPException):
    def __init__(self, detail: Any = None, status_code: int = 403):
        super().__init__(status_code=status_code, detail=detail)


AccessGuardListener = Callable[[type, ModelAction, Any], "Awaitable[None] | None"]
AccessGuardApply = Callable[[type], bool] | None

_C = TypeVar("_C", bound=type)


@dataclass(frozen=True)
class AccessGuard:
    listener: AccessGuardListener
    apply: AccessGuardApply = None


class ModelAccessGuardRegistry:
    """Registry of access-guard listeners invoked on every CRUD action of a managed model.

    Listeners are synchronous callables that raise (typically :class:`AccessDeniedError`)
    to deny the action. They receive the written instance on the write path (save/
    delete) and ``None`` on the read path, enabling row-conditional write rules. A listener may return an awaitable to perform async work: it is
    awaited on the write path (``acheck_access``, called from ``save``/``delete``), and
    rejected on the read path (``check_access``, called from the synchronous
    ``get_queryset`` hook).
    """

    def __init__(self):
        self._guards: dict[type, list[AccessGuard]] = {}
        self._resolved: dict[type, tuple[AccessGuard, ...]] = {}

    def register(
        self,
        model_cls: type,
        listener: AccessGuardListener,
        apply: AccessGuardApply = None,
    ) -> None:
        self._guards.setdefault(model_cls, []).append(AccessGuard(listener, apply))
        self._resolved.clear()

    def get_guards(self, model_cls: type) -> tuple[AccessGuard, ...]:
        guards = self._resolved.get(model_cls)

        if guards is None:
            guards = tuple(guard for klass in model_cls.__mro__ for guard in self._guards.get(klass, ()))
            self._resolved[model_cls] = guards

        return guards

    def has_guards(self, model_cls: type) -> bool:
        return bool(self.get_guards(model_cls))

    def check_access(self, model_cls: type, action: ModelAction, instance: Any = None) -> None:
        for guard in self.get_guards(model_cls):
            if guard.apply is not None and not guard.apply(model_cls):
                continue

            result = guard.listener(model_cls, action, instance)

            if result is not None:
                result.close()  # type: ignore[union-attr]
                raise RuntimeError(
                    f"Access guard listener {guard.listener!r} returned an awaitable for the "
                    f"synchronous '{action.value}' check on {model_cls.__name__}; async guards "
                    "are only supported on write actions."
                )

    async def acheck_access(self, model_cls: type, action: ModelAction, instance: Any = None) -> None:
        for guard in self.get_guards(model_cls):
            if guard.apply is not None and not guard.apply(model_cls):
                continue

            result = guard.listener(model_cls, action, instance)

            if result is not None:
                await result


register_service(ModelAccessGuardRegistry)


def access_guard(
    listener: AccessGuardListener,
    apply: AccessGuardApply = None,
) -> Callable[[_C], _C]:
    def decorator(cls: _C) -> _C:
        get_service(ModelAccessGuardRegistry).register(cls, listener, apply)
        return cls

    return decorator


def check_access(model_cls: type, action: ModelAction, instance: Any = None) -> None:
    get_service(ModelAccessGuardRegistry).check_access(model_cls, action, instance)


async def acheck_access(model_cls: type, action: ModelAction, instance: Any = None) -> None:
    await get_service(ModelAccessGuardRegistry).acheck_access(model_cls, action, instance)


__all__ = [
    "ModelAction",
    "AccessDeniedError",
    "AccessGuard",
    "AccessGuardListener",
    "AccessGuardApply",
    "ModelAccessGuardRegistry",
    "access_guard",
    "check_access",
    "acheck_access",
]
