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
    )
    from fastedgy import (
        app as app,
    )
    from fastedgy import (
        bus as bus,
    )
    from fastedgy import (
        cli as cli,
    )
    from fastedgy import (
        config as config,
    )
    from fastedgy import (
        context as context,
    )
    from fastedgy import (
        dataflow as dataflow,
    )
    from fastedgy import (
        dependencies as dependencies,
    )
    from fastedgy import (
        http as http,
    )
    from fastedgy import (
        lifecycle as lifecycle,
    )
    from fastedgy import (
        logger as logger,
    )
    from fastedgy import (
        metadata_model as metadata_model,
    )
    from fastedgy import (
        modules as modules,
    )
    from fastedgy import (
        orm as orm,
    )
    from fastedgy import (
        schemas as schemas,
    )
    from fastedgy import (
        storage as storage,
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
    "app",
    "bus",
    "cli",
    "config",
    "context",
    "dataflow",
    "dependencies",
    "http",
    "lifecycle",
    "logger",
    "metadata_model",
    "modules",
    "orm",
    "schemas",
    "storage",
]
