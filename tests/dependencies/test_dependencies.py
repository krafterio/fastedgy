# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Tests for the dependency-injection container (``fastedgy.dependencies``).

The registry and resolution cache are process-global, so an autouse fixture
snapshots and restores them around every test to keep the suite isolated and to
never leak dummy services into the real application registry.

The forward-reference cases rely on module-level consumer classes whose
annotations name types that are NOT importable from this module: ``get_type_hints``
then fails and the resolver falls back to the raw string annotation, which is the
branch under test.
"""

from typing import TYPE_CHECKING

import pytest

from fastedgy import dependencies as di
from fastedgy.dependencies import (
    Inject,
    Token,
    get_service,
    has_service,
    provide,
    register_service,
    unregister_service,
)


@pytest.fixture(autouse=True)
def isolated_registry():
    saved_registry = dict(di._services_registry)
    saved_cache = dict(di._dependencies_cache)
    di._services_registry.clear()
    di._dependencies_cache.clear()

    try:
        yield
    finally:
        di._services_registry.clear()
        di._services_registry.update(saved_registry)
        di._dependencies_cache.clear()
        di._dependencies_cache.update(saved_cache)


if TYPE_CHECKING:

    class ForwardOnlyService:
        pass

    class TotallyUnknownService:
        pass

    UnknownService = str


class ConsumerWithForwardRef:
    def __init__(self, dep: "ForwardOnlyService"):
        self.dep = dep


class ConsumerWithDefaultedForwardRef:
    def __init__(self, dep: "UnknownService" = "fallback"):
        self.dep = dep


class ConsumerWithBrokenForwardRef:
    def __init__(self, dep: "TotallyUnknownService"):
        self.dep = dep


# --- Token -----------------------------------------------------------------------


def test_token_from_string_key():
    token = Token("config")

    assert token.key == "config"
    assert token.name == "config"
    assert repr(token) == "Token('config')"


def test_token_from_type_key():
    class Svc:
        pass

    token = Token(Svc)

    assert token.key is Svc
    assert token.name == "Svc"
    assert repr(token) == "Token(Svc)"


def test_token_equality_and_hashing():
    assert Token("svc") == Token("svc")
    assert hash(Token("svc")) == hash(Token("svc"))
    assert Token("a") != Token("b")

    class Foo:
        pass

    assert Token(Foo) == Token(Foo)
    assert {Token("k"): 1}[Token("k")] == 1


def test_token_not_equal_to_non_token():
    assert Token("svc") != "svc"
    assert (Token("svc") == 123) is False


def test_token_generic_subscription_returns_distinct_subclass():
    subscripted = Token[int]

    assert issubclass(subscripted, Token)
    assert subscripted is not Token
    assert Token[int] is not Token[int]


# --- register / get --------------------------------------------------------------


def test_registered_class_is_instantiated_as_cached_singleton():
    class Svc:
        pass

    register_service(Svc)
    first = get_service(Svc)
    second = get_service(Svc)

    assert isinstance(first, Svc)
    assert first is second


def test_registered_instance_is_returned_as_is():
    class Svc:
        pass

    instance = Svc()
    register_service(instance)

    assert get_service(Svc) is instance


def test_get_service_auto_registers_unknown_class():
    class Svc:
        pass

    assert not has_service(Svc)
    instance = get_service(Svc)

    assert isinstance(instance, Svc)
    assert has_service(Svc)


def test_register_is_idempotent_without_force():
    class Svc:
        pass

    first, second = Svc(), Svc()
    register_service(first)
    register_service(second)

    assert get_service(Svc) is first


def test_register_with_force_overrides():
    class Svc:
        pass

    first, second = Svc(), Svc()
    register_service(first)
    register_service(second, force=True)

    assert get_service(Svc) is second


def test_register_instance_under_string_key():
    class Svc:
        pass

    instance = Svc()
    register_service(instance, key="my_key")

    assert get_service("my_key") is instance


def test_register_instance_under_explicit_token_key():
    class Svc:
        pass

    instance = Svc()
    token = Token("tok")
    register_service(instance, key=token)

    assert get_service(token) is instance


def test_class_key_and_token_key_are_equivalent():
    class Svc:
        pass

    instance = Svc()
    register_service(instance, key=Token(Svc))

    assert get_service(Svc) is instance
    assert get_service(Token(Svc)) is instance


# --- has_service / unregister_service --------------------------------------------


def test_has_service_reflects_registration():
    class Svc:
        pass

    assert not has_service(Svc)
    register_service(Svc)
    assert has_service(Svc)


def test_unregister_removes_service():
    class Svc:
        pass

    register_service(Svc)
    unregister_service(Svc)

    assert not has_service(Svc)


def test_unregister_unknown_is_noop():
    class Svc:
        pass

    unregister_service(Svc)

    assert not has_service(Svc)


# --- dependency resolution -------------------------------------------------------


def test_constructor_without_dependencies():
    class Svc:
        def __init__(self):
            self.ready = True

    register_service(Svc)

    assert get_service(Svc).ready is True


def test_service_dependency_is_injected_as_singleton():
    class Dep:
        pass

    class Consumer:
        def __init__(self, dep: Dep):
            self.dep = dep

    register_service(Dep)
    register_service(Consumer)
    dep_singleton = get_service(Dep)

    assert get_service(Consumer).dep is dep_singleton


def test_missing_service_dependency_is_auto_registered():
    class Dep:
        pass

    class Consumer:
        def __init__(self, dep: Dep):
            self.dep = dep

    register_service(Consumer)
    consumer = get_service(Consumer)

    assert isinstance(consumer.dep, Dep)
    assert has_service(Dep)


def test_nested_dependency_chain_is_resolved():
    class C:
        pass

    class B:
        def __init__(self, c: C):
            self.c = c

    class A:
        def __init__(self, b: B):
            self.b = b

    for cls in (A, B, C):
        register_service(cls)

    a = get_service(A)

    assert isinstance(a.b, B)
    assert isinstance(a.b.c, C)
    assert a.b is get_service(B)
    assert a.b.c is get_service(C)


def test_defaulted_scalar_param_keeps_its_default():
    """Regression: a defaulted scalar must not be clobbered with a zero-value."""

    class Configured:
        def __init__(self, *, channel: str = "ws_broadcast"):
            self.channel = channel

    register_service(Configured)

    assert get_service(Configured).channel == "ws_broadcast"


def test_defaulted_params_of_all_scalar_types_keep_defaults():
    """Regression: str/int/float/bool defaults survive resolution (no '', 0, 0.0, False)."""

    class Tuned:
        def __init__(self, *, name: str = "x", count: int = 4, ratio: float = 1.5, enabled: bool = True):
            self.name = name
            self.count = count
            self.ratio = ratio
            self.enabled = enabled

    register_service(Tuned)
    tuned = get_service(Tuned)

    assert (tuned.name, tuned.count, tuned.ratio, tuned.enabled) == ("x", 4, 1.5, True)


def test_defaulted_param_is_injected_when_its_type_is_a_registered_service():
    class Dep:
        pass

    class Consumer:
        def __init__(self, dep: Dep = Dep()):
            self.dep = dep

    register_service(Dep)
    register_service(Consumer)

    assert get_service(Consumer).dep is get_service(Dep)


def test_required_scalar_param_without_default_resolves_to_zero_value():
    """Documents current behaviour: an un-defaulted scalar is treated as a dependency
    and auto-instantiated to its zero-value (str -> '')."""

    class NeedsName:
        def __init__(self, name: str):
            self.name = name

    register_service(NeedsName)

    assert get_service(NeedsName).name == ""


def test_resolution_is_cached_across_calls():
    class Dep:
        pass

    class Consumer:
        def __init__(self, dep: Dep):
            self.dep = dep

    register_service(Dep)
    register_service(Consumer)

    assert get_service(Consumer) is get_service(Consumer)
    assert get_service(Consumer).dep is get_service(Dep)


def test_unresolved_forward_ref_matches_registered_service_by_name():
    class ForwardOnlyService:
        pass

    register_service(ForwardOnlyService)
    register_service(ConsumerWithForwardRef)

    assert isinstance(get_service(ConsumerWithForwardRef).dep, ForwardOnlyService)


def test_unresolved_forward_ref_with_default_uses_default():
    register_service(ConsumerWithDefaultedForwardRef)

    assert get_service(ConsumerWithDefaultedForwardRef).dep == "fallback"


def test_unresolved_required_forward_ref_is_not_injected():
    """Documents the quoted-forward-ref footgun: an unresolvable required ref is
    silently skipped, so construction fails for the missing argument."""
    register_service(ConsumerWithBrokenForwardRef)

    with pytest.raises(TypeError):
        get_service(ConsumerWithBrokenForwardRef)


# --- provide / Inject ------------------------------------------------------------


def test_provide_returns_callable_resolving_singleton():
    class Svc:
        pass

    register_service(Svc)
    dep = provide(Svc)

    assert callable(dep)
    assert dep() is get_service(Svc)


def test_inject_returns_fastapi_depends_resolving_the_service():
    from fastapi.params import Depends as DependsParam

    class Svc:
        pass

    register_service(Svc)
    injected = Inject(Svc)

    assert isinstance(injected, DependsParam)
    assert injected.dependency is not None
    assert injected.dependency() is get_service(Svc)


async def test_inject_resolves_service_in_a_fastapi_endpoint():
    import httpx
    from fastapi import FastAPI

    class Conf:
        def __init__(self):
            self.value = "injected"

    register_service(Conf)

    app = FastAPI()

    @app.get("/value")
    def read_value(conf: Conf = Inject(Conf)):
        return {"value": conf.value}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/value")

    assert response.status_code == 200
    assert response.json() == {"value": "injected"}
