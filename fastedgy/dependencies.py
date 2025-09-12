# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import FastAPI, Depends
from contextlib import AsyncExitStack
from typing import Callable, TypeVar, Any, MutableMapping, Type, cast, Union, Generic, Dict
from fastapi.dependencies.utils import get_dependant, solve_dependencies as base_solve_dependencies
from starlette.requests import Request


T = TypeVar('T')


class Token(Generic[T]):
    """Token for string-based service registration."""
    def __init__(self, name: str):
        self.name = name

    def __class_getitem__(cls, item):
        """Allow Token[SomeType]('name') syntax."""
        class TypedToken(Token):
            pass
        return TypedToken

    def __repr__(self):
        return f"Token({self.name})"

    def __hash__(self):
        return hash(("__token__", self.name))

    def __eq__(self, other):
        return isinstance(other, Token) and other.name == self.name


ProviderKey = Union[Type[Any], Token[Any]]


async def depends(app: FastAPI | None, call: Callable[..., T]) -> T:
    values = await solve_dependencies(app, None, call)

    return call(**values)


async def solve_dependencies(app: FastAPI | None, request: Request | None, call: Callable[..., T], skip_error: bool = False) -> dict[str, Any]:
    if not request:
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
        })
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
        self._map: Dict[ProviderKey, Any] = {}
        # Support for FastAPI overrides
        self.dependency_overrides: MutableMapping[Any, Any] = {}

    def register(self, key: ProviderKey, instance: T) -> T:
        if key not in self._map:
            self._map[key] = instance

        return self._map[key]

    def get(self, key: ProviderKey) -> T:
        try:
            return cast(T, self._map[key])
        except KeyError as e:
            raise LookupError(f"No instance registered for {key!r}") from e


container_service = ContainerService()


def get_container_service() -> ContainerService:
    return container_service


def register_service(instance: T, key: Union[Type[T], Token[T], str, None] = None) -> None:
    if key is None:
        key = type(instance)
    elif isinstance(key, str):
        key = Token(key)

    container_service.register(key, instance)


def get_service(key: Union[Type[T], Token[T], str]) -> T:
    if isinstance(key, str):
        key = Token(key)
    return container_service.get(key)


def provide(cls: Union[Type[T], Token[T], str]) -> Callable[[ContainerService], T]:
    """Use in FastAPI signatures: svc: Svc = Depends(provide(Svc))"""
    def dep(container: ContainerService = Depends(get_container_service)) -> T:
        if isinstance(cls, str):
            return container.get(Token(cls))
        return container.get(cls)

    return dep


def Inject(cls: Union[Type[T], Token[T], str]) -> T:
    """Use in FastAPI signatures: svc: Svc = Inject(Svc)"""
    return Depends(provide(cls))


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
