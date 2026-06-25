# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import importlib

from typing import TYPE_CHECKING, Any

# Submodules are imported lazily (PEP 562): importing ``fastedgy`` no longer pulls
# the whole framework (FastAPI, the ORM, Alembic, the api_route_model machinery, ...).
# Each submodule loads only when it is first accessed, which keeps CLI startup and
# ``from fastedgy.x import ...`` cheap.
_SUBMODULES = frozenset(
    {
        "api_route_model",
        "cli",
        "metadata_model",
        "orm",
        "schemas",
        "app",
        "config",
        "context",
        "dataflow",
        "dependencies",
        "bus",
        "http",
        "modules",
        "logger",
        "storage",
        "lifecycle",
    }
)

if TYPE_CHECKING:
    from fastedgy import (
        api_route_model as api_route_model,
        cli as cli,
        metadata_model as metadata_model,
        orm as orm,
        schemas as schemas,
        app as app,
        config as config,
        context as context,
        dataflow as dataflow,
        dependencies as dependencies,
        bus as bus,
        http as http,
        modules as modules,
        logger as logger,
        storage as storage,
        lifecycle as lifecycle,
    )


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULES)


__all__ = [
    "api_route_model",
    "cli",
    "metadata_model",
    "orm",
    "schemas",
    "app",
    "config",
    "context",
    "dataflow",
    "dependencies",
    "bus",
    "http",
    "modules",
    "logger",
    "storage",
    "lifecycle",
]
