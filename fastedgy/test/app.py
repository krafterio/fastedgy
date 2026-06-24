# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

from fastapi import APIRouter

from fastedgy.app import FastEdgy
from fastedgy.api_route_model.router import register_api_route_models
from fastedgy.api_route_model.standard_actions import (
    register_standard_api_route_model_actions,
)
from fastedgy.dependencies import get_service
from fastedgy.orm import Registry

from fastedgy.test.models import ALL_MODELS


APP_TITLE = "FastEdgy Test API"
APP_VERSION = "0.0.0-test"
APP_DESCRIPTION = "Synthetic FastEdgy application used as the OpenAPI regression fixture."
API_PREFIX = "/api"

_standard_actions_registered = False


def _ensure_standard_actions() -> None:
    global _standard_actions_registered

    if not _standard_actions_registered:
        register_standard_api_route_model_actions()
        _standard_actions_registered = True


def build_app() -> FastEdgy:
    _ensure_standard_actions()

    app = FastEdgy(version=APP_VERSION)

    get_service(Registry).init_models()

    api_router = APIRouter(prefix=API_PREFIX)
    register_api_route_models(api_router)
    app.include_router(api_router)

    app.title = APP_TITLE
    app.summary = None
    app.description = APP_DESCRIPTION
    app.version = APP_VERSION
    app.openapi_schema = None

    return app


def dump_openapi(app: FastEdgy) -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


__all__ = [
    "APP_TITLE",
    "APP_VERSION",
    "APP_DESCRIPTION",
    "API_PREFIX",
    "ALL_MODELS",
    "build_app",
    "dump_openapi",
]
