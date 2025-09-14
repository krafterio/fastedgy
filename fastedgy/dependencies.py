# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import FastAPI, Depends
from contextlib import AsyncExitStack
from typing import (
    Callable,
    TypeVar,
    Any,
    MutableMapping,
    Type,
    cast,
    Union,
    Generic,
    Dict,
)
from fastapi.dependencies.utils import (
    get_dependant,
    solve_dependencies as base_solve_dependencies,
)
from starlette.requests import Request


T = TypeVar("T")


class Token(Generic[T]):
    """Token for service registration using string names or class types."""

    def __init__(self, key: Union[str, Type[Any]]):
        self.key = key
        self.name = key if isinstance(key, str) else key.__name__

    def __class_getitem__(cls, item):
        class TypedToken(Token):
            pass

        return TypedToken

    def __repr__(self):
        if isinstance(self.key, str):
            return f"Token({self.key!r})"
        else:
            return f"Token({self.key.__name__})"

    def __hash__(self):
        if isinstance(self.key, str):
            return hash(("__token__", self.key))
        else:
            return hash(("__token__", self.key))

    def __eq__(self, other):
        return isinstance(other, Token) and other.key == self.key


ProviderKey = Union[Type[Any], Token[Any]]


async def depends(app: FastAPI | None, call: Callable[..., T]) -> T:
    values = await solve_dependencies(app, None, call)

    return call(**values)


async def solve_dependencies(
    app: FastAPI | None,
    request: Request | None,
    call: Callable[..., T],
    skip_error: bool = False,
) -> dict[str, Any]:
    if not request:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "headers": [],
            }
        )
    dependant = get_dependant(path="", call=call)
    exit_stack = AsyncExitStack()
    solved = await base_solve_dependencies(
        request=request,
        dependant=dependant,
        dependency_overrides_provider=app,
        async_exit_stack=exit_stack,
        embed_body_fields=False,
    )
    await exit_stack.aclose()

    if solved.errors and not skip_error:
        raise RuntimeError(f"Dependency Injection Error: {solved.errors}")

    return solved.values


class ContainerService:
    """Container service for the application."""

    def __init__(self) -> None:
        self._map: Dict[ProviderKey, Union[Any, Callable[[], Any]]] = {}
        # Support for FastAPI overrides
        self.dependency_overrides: MutableMapping[Any, Any] = {}

    def register(
        self, key: ProviderKey, instance: Union[T, Callable[[], T]], force: bool = False
    ) -> None:
        if force or key not in self._map:
            self._map[key] = instance

    def unregister(self, key: ProviderKey) -> None:
        if key in self._map:
            del self._map[key]

    def has(self, key: ProviderKey) -> bool:
        return key in self._map

    def get(self, key: ProviderKey) -> T:
        try:
            value = self._map[key]

            if callable(value):
                instance = value()
                self._map[key] = instance

                return cast(T, instance)

            return cast(T, value)
        except KeyError as e:
            raise LookupError(f"No instance registered for {key!r}") from e


container_service = ContainerService()


def get_container_service() -> ContainerService:
    return container_service


def register_service(
    instance: Union[T, Callable[[], T]],
    key: Union[Type[T], Token[T], str, None] = None,
    force: bool = False,
) -> None:
    if callable(instance):
        if key is None:
            raise ValueError("Key must be provided when registering a callable")

        provided_key = _normalize_key(key)
        container_service.register(provided_key, instance)
    else:
        instance_type_key = _normalize_key(type(instance))
        provided_key = _normalize_key(type(instance) if key is None else key)

        container_service.register(provided_key, instance)

        if instance_type_key != provided_key:
            container_service.register(instance_type_key, instance, force)


def unregister_service(key: Union[Type[T], Token[T], str]) -> None:
    container_service.unregister(_normalize_key(key))


def has_service(key: Union[Type[T], Token[T], str]) -> bool:
    return container_service.has(_normalize_key(key))


def get_service(key: Union[Type[T], Token[T], str]) -> T:
    return container_service.get(_normalize_key(key))


def provide(cls: Union[Type[T], Token[T], str]) -> Callable[[ContainerService], T]:
    """Use in FastAPI signatures: svc: Svc = Depends(provide(Svc))"""

    def dep(container: ContainerService = Depends(get_container_service)) -> T:
        return container.get(_normalize_key(cls))

    return dep


def Inject(cls: Union[Type[T], Token[T], str]) -> T:
    """Use in FastAPI signatures: svc: Svc = Inject(Svc)"""
    return Depends(provide(cls))


def _normalize_key(
    key: Union[Type[Any], Token[Any], str],
) -> Union[Token[Any], Type[Any]]:
    if isinstance(key, str) or isinstance(key, type):
        return Token(key)

    return key


__all__ = [
    "depends",
    "solve_dependencies",
    "ContainerService",
    "get_container_service",
    "register_service",
    "get_service",
    "provide",
    "Inject",
    "Token",
    "ProviderKey",
]
