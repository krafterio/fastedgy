# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import importlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service

_INSTALLED_DIRECTORIES = {"site-packages", "dist-packages"}


class TaskFunctionError(ValueError):
    pass


def _is_application_code(location: str, root: Path) -> bool:
    path = Path(location).resolve()

    return path.is_relative_to(root) and not _INSTALLED_DIRECTORIES & set(path.parts)


def is_task_module(module_name: str) -> bool:
    top = module_name.partition(".")[0]

    if top == "fastedgy" or top.startswith("fastedgy_"):
        return True

    if not top or top in sys.stdlib_module_names:
        return False

    try:
        spec = importlib.util.find_spec(top)
    except ImportError, ValueError:
        return False

    if spec is None:
        return False

    locations = list(spec.submodule_search_locations or []) or ([spec.origin] if spec.origin else [])
    root = Path(get_service(BaseSettings).server_path).resolve()

    return bool(locations) and all(_is_application_code(location, root) for location in locations)


def resolve_task_function(module_name: str, function_name: str) -> Callable[..., Any]:
    if not is_task_module(module_name):
        raise TaskFunctionError(f"'{module_name}' holds no task function")

    func = getattr(importlib.import_module(module_name), function_name, None)

    if not callable(func) or not is_task_module(getattr(func, "__module__", None) or ""):
        raise TaskFunctionError(f"'{module_name}.{function_name}' is not a task function")

    return func


__all__ = [
    "TaskFunctionError",
    "is_task_module",
    "resolve_task_function",
]
