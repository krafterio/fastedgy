# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import sys
from pathlib import Path
from pydantic_settings import BaseSettings as PydanticBaseSettings, SettingsConfigDict


SERVER_FILES = [
    "__init__.py",
    "__main__.py",
    "main.py",
    "app.py",
]


SETTINGS_PACKAGES = [
    "config:Settings",
    "config:AppSettings",
    "settings:Settings",
    "settings:AppSettings",
    "main:Settings",
    "main:AppSettings",
    "app:Settings",
    "app:AppSettings",
]


def _find_project_path() -> str:
    """Find project root by looking for pyproject.toml in current dir and parents."""
    current = Path.cwd()

    for path in [current] + list(current.parents):
        if (path / "pyproject.toml").exists():
            return str(path)

    return str(current)


def _find_server_path() -> str:
    """Find server directory by looking for app files in current dir or direct children."""
    current = Path.cwd()

    for file_name in SERVER_FILES:
        if (current / file_name).exists():
            return str(current)

    try:
        for child in current.iterdir():
            if child.is_dir() and not child.name.startswith('.'):
                for file_name in SERVER_FILES:
                    if (child / file_name).exists():
                        return str(child)
    except PermissionError:
        pass

    return str(current)


_PROJECT_PATH = _find_project_path()
_SERVER_PATH = _find_server_path()


if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)


def discover_settings_class():
    """
    Discover and return project settings class.

    Searches for custom settings in project and falls back to BaseSettings if not found.
    """
    from fastedgy.importer import import_from_string, ImportFromStringError

    for settings_package in SETTINGS_PACKAGES:
        try:
            settings_class = import_from_string(settings_package)
            if settings_class and issubclass(settings_class, BaseSettings):
                return settings_class
        except (ImportFromStringError, AttributeError, TypeError):
            continue

    return BaseSettings


class BaseSettings(PydanticBaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix='',
        extra='ignore',
    )

    app_factory: str = "main:app"
    title: str = "FastEdgy"

    @classmethod
    def from_env_file(cls, env_file: str):
        """Create Settings with custom env file path."""
        return cls(_env_file=env_file)  # type: ignore

    @property
    def project_path(self) -> str:
        """Get the project root path."""
        return _PROJECT_PATH

    @property
    def server_path(self) -> str:
        """Get the server directory path."""
        return _SERVER_PATH


__all__ = [
    "BaseSettings",
    "discover_settings_class",
]
