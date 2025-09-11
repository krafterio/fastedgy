# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from functools import cached_property
import sys
import os

from pathlib import Path
from typing import Type
from urllib.parse import urlparse
from pydantic import field_validator
from pydantic_settings import BaseSettings as PydanticBaseSettings, SettingsConfigDict
from edgy import Database, Registry

from fastedgy.logger import LogLevel, LogOutput, LogFormat

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

    http_workers: int | None = None

    log_level: LogLevel = LogLevel.INFO
    log_output: LogOutput = LogOutput.CONSOLE
    log_format: LogFormat | str = LogFormat.TEXT_LIGHT
    log_file: str = ''

    database_url: str = ''
    database_pool_size: int = 20
    database_max_overflow: int = 10


    @classmethod
    def from_env_file(cls, env_file: str):
        """Create Settings with custom env file path."""
        return cls(_env_file=env_file)  # type: ignore

    def initialize(self) -> None:
        pass

    @property
    def project_path(self) -> str:
        """Get the project root path."""
        return _PROJECT_PATH

    @property
    def server_path(self) -> str:
        """Get the server directory path."""
        return _SERVER_PATH

    @property
    def log_path(self) -> str:
        if not self.log_file:
            return os.path.join(self.project_path, "logs", "server.log")

        if os.path.isabs(self.log_file):
            return self.log_file

        return os.path.join(self.project_path, self.log_file)

    @property
    def db_migration_path(self) -> str:
        return os.path.join(self.server_path, "migrations")

    @property
    def db_name(self) -> str:
        return urlparse(self.database_url).path.lstrip('/')

    @cached_property
    def db(self) -> Database:
        return Database(
            self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
        )

    @cached_property
    def db_registry(self) -> Registry:
        return Registry(self.db)

    @field_validator('log_format')
    def validate_log_format(cls, v):
        if isinstance(v, str) and v in [item.value for item in LogFormat]:
            return LogFormat(v)
        return v

    @field_validator('database_url')
    def validate_database_url(cls, v):
        if v:
            return v
        raise ValueError('DATABASE_URL is required')


_settings: BaseSettings | None = None


def get_settings(env_file: str | None = None):
    global _settings

    if _settings is None:
        import hashlib
        import os

        sha = hashlib.sha256(__file__.encode()).hexdigest()[:12]
        existing_env_file = f"FASTEDGY_ENV_FILE_{sha}"

        if existing_env_file in os.environ:
            env_file = os.environ[existing_env_file]
        else:
            if not env_file:
                env_file = ".env"

            os.environ[existing_env_file] = env_file

        from fastedgy.config import BaseSettings, discover_settings_class
        settings_class: Type[BaseSettings] = discover_settings_class()
        _settings = settings_class.from_env_file(env_file)

    return _settings


__all__ = [
    "BaseSettings",
    "discover_settings_class",
    "get_settings",
]
