# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import importlib
import json

from fastapi import APIRouter

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.router import register_api_route_models
from fastedgy.api_route_model.standard_actions import (
    register_standard_api_route_model_actions,
)
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry


APP_TITLE = "FastEdgy Test API"
APP_VERSION = "0.0.0-test"
APP_DESCRIPTION = "Synthetic FastEdgy application used as the OpenAPI regression fixture."
API_PREFIX = "/api"

_standard_actions_registered = False
_app: FastEdgy | None = None


def _ensure_standard_actions() -> None:
    global _standard_actions_registered

    if not _standard_actions_registered:
        register_standard_api_route_model_actions()
        _standard_actions_registered = True


def build_app() -> FastEdgy:
    # The app (and its registry) is built once per process: rebuilding it would
    # churn the registry service and break runtime model lookups via Inject.
    global _app

    if _app is not None:
        return _app

    from fastapi import Depends

    from fastedgy.api import auth, auth_simple_registration, dataset, health, storage
    from fastedgy.depends.security import get_current_user

    # Imported here (not at module top) for its registration side effect: merely
    # importing fastedgy.test must not register the synthetic models, so a
    # downstream project can build its own app without a registry collision.
    importlib.import_module("fastedgy.test.models")

    _ensure_standard_actions()

    app = FastEdgy(version=APP_VERSION)

    get_service(Registry).init_models()

    # Public routes (no authentication required).
    public_router = APIRouter(prefix=API_PREFIX)
    public_router.include_router(auth_simple_registration.router)
    public_router.include_router(auth.public_router)

    # Authenticated routes: everything below requires a valid access token,
    # mirroring how a real FastEdgy application is wired.
    router = APIRouter(prefix=API_PREFIX, dependencies=[Depends(get_current_user)])
    router.include_router(auth.router)
    router.include_router(dataset.router)
    router.include_router(health.router)
    router.include_router(storage.attachments_router)
    router.include_router(storage.manage_attachments_router)
    router.include_router(storage.router)
    router.include_router(storage.manage_router)
    register_api_route_models(router)

    app.include_router(public_router)
    app.include_router(router)

    app.title = APP_TITLE
    app.summary = None
    app.description = APP_DESCRIPTION
    app.version = APP_VERSION
    app.openapi_schema = None

    _app = app

    return app


def load_app() -> FastEdgy:
    """Resolve the application under test the way the HTTP workers do.

    Uses ``settings.app_factory`` (e.g. ``main:app``) so a downstream project's
    test suite runs against its real app. Falls back to the framework's synthetic
    app when no project app is importable (FastEdgy's own test suite).
    """
    from fastedgy.config import init_settings
    from fastedgy.modules import ImportFromStringError, import_from_string

    try:
        settings = init_settings()
        factory = import_from_string(settings.app_factory)
    except (ImportFromStringError, ImportError, AttributeError, ValueError):
        return build_app()

    return factory()


def dump_openapi(app: FastEdgy) -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


__all__ = [
    "APP_TITLE",
    "APP_VERSION",
    "APP_DESCRIPTION",
    "API_PREFIX",
    "build_app",
    "load_app",
    "dump_openapi",
]
