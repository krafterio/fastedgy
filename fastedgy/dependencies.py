# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastapi import Depends
from typing import (
    Callable,
    TypeVar,
    Any,
    Type,
    cast,
    Union,
    Generic,
    Dict,
)


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


_services_registry: Dict[ProviderKey, Union[Any, Type[Any]]] = {}
_dependencies_cache: Dict[tuple[Callable[..., Any], tuple[str]], Any] = {}


def register_service(
    instance: Union[T, Type[T]],
    key: Union[Type[T], Token[T], str, None] = None,
    force: bool = False,
) -> None:
    """
    Register a service (class or instance) in the registry.
    - If instance is a class: will be resolved when requested
    - If instance is an object: will be returned as-is (singleton)
    """
    import inspect

    if inspect.isclass(instance):
        provided_key = _normalize_key(instance if key is None else key)
        _register_service(provided_key, instance, force)
    else:
        instance_type_key = _normalize_key(type(instance))
        provided_key = _normalize_key(type(instance) if key is None else key)

        _register_service(provided_key, instance, force)

        if key is None and instance_type_key != provided_key:
            _register_service(instance_type_key, instance, force)


def unregister_service(key: Union[Type[T], Token[T], str]) -> None:
    """Unregister a service from the registry."""
    _unregister_service(_normalize_key(key))


def has_service(key: Union[Type[T], Token[T], str]) -> bool:
    """Check if a service is registered."""
    return _has_service(_normalize_key(key))


def get_service(key: Union[Type[T], Token[T], str]) -> T:
    """
    Get a service instance from the registry.
    Auto-registers classes if not already registered.
    """
    normalized_key = _normalize_key(key)

    if not _has_service(normalized_key) and isinstance(key, type):
        register_service(key)

    value = _services_registry[normalized_key]

    if not isinstance(value, type) and not callable(value):
        return cast(T, value)

    if not isinstance(value, type):
        raise LookupError(f"Service {key} is not a class and cannot be resolved")

    service_class = value
    cache_key = (normalized_key, service_class, ())

    if cache_key in _dependencies_cache:
        return _dependencies_cache[cache_key]

    kwargs = _resolve_dependencies(service_class)
    instance = service_class(**kwargs)

    _dependencies_cache[cache_key] = instance

    return instance


def provide(cls: Union[Type[T], Token[T], str]) -> Callable[[], T]:
    """Use in FastAPI signatures: svc: Svc = Depends(provide(Svc))"""

    def dep() -> T:
        return get_service(cls)

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


def _has_service(key: ProviderKey) -> bool:
    """Check if a service is registered."""
    return key in _services_registry


def _register_service(
    key: ProviderKey, instance: Union[Any, Type[Any]], force: bool = False
) -> None:
    """Internal function to register a service in the registry."""
    if force or key not in _services_registry:
        _services_registry[key] = instance


def _unregister_service(key: ProviderKey) -> None:
    """Internal function to unregister a service from the registry."""
    if key in _services_registry:
        del _services_registry[key]


def _resolve_dependencies(service_class: Type[T]) -> Dict[str, Any]:
    """
    Resolve service dependencies by inspecting __init__ parameters.
    Handles both direct type annotations and string annotations (TYPE_CHECKING).
    """
    import inspect
    import sys
    from typing import get_type_hints

    sig = inspect.signature(service_class.__init__)
    kwargs = {}

    type_hints = {}
    try:
        module = sys.modules.get(service_class.__module__)
        globalns = getattr(module, "__dict__", {}) if module else {}
        type_hints = get_type_hints(
            service_class.__init__, globalns=globalns, localns=None
        )
    except (NameError, Exception):
        pass

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        param_type = type_hints.get(param_name, param.annotation)

        if isinstance(param_type, str):
            for key in _services_registry.keys():
                if isinstance(key, type) and key.__name__ == param_type:
                    param_type = key
                    break
                elif isinstance(key, Token):
                    token_key = key.key
                    if isinstance(token_key, type) and token_key.__name__ == param_type:
                        param_type = token_key
                        break

        if param_type == inspect.Parameter.empty or isinstance(param_type, str):
            if param.default != inspect.Parameter.empty:
                kwargs[param_name] = param.default
            continue

        try:
            kwargs[param_name] = get_service(param_type)
        except LookupError:
            if param.default != inspect.Parameter.empty:
                kwargs[param_name] = param.default

    return kwargs


__all__ = [
    "register_service",
    "unregister_service",
    "has_service",
    "get_service",
    "provide",
    "Inject",
    "Token",
    "ProviderKey",
]
