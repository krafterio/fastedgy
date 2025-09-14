# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import sys
import os

from functools import cached_property
from pathlib import Path
from typing import Annotated, Type
from urllib.parse import urlparse
from fastedgy.dependencies import Inject, get_service, has_service, register_service
from fastedgy.logger import LogLevel, LogOutput, LogFormat
from pydantic import field_validator
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
            if child.is_dir() and not child.name.startswith("."):
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
        env_prefix="",
        extra="ignore",
    )

    # App factory
    app_factory: str = "main:app"

    # App
    title: str = "FastEdgy"
    base_url_app: str = ""

    # HTTP
    http_workers: int | None = None

    # Logging
    log_level: LogLevel = LogLevel.INFO
    log_output: LogOutput = LogOutput.CONSOLE
    log_format: LogFormat | str = LogFormat.TEXT_LIGHT
    log_file: str = ""

    # Database
    database_url: str = ""
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Auth
    auth_secret_key: str = ""
    auth_algorithm: str = "HS256"
    auth_access_token_expire_minutes: int = 15
    auth_refresh_token_expire_days: int = 30

    # Storage
    data_path: str | None = None

    # Mail
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_default_from: str = ""

    # I18n
    fallback_locale: str = "en"
    available_locales: list[str] = ["en"]
    translations_paths: list[str] = []

    @classmethod
    def from_env_file(cls, env_file: str):
        """Create Settings with custom env file path."""
        return cls(_env_file=env_file)

    @property
    def project_path(self) -> str:
        """Get the project root path."""
        return _PROJECT_PATH

    @property
    def server_path(self) -> str:
        """Get the server directory path."""
        return _SERVER_PATH

    @cached_property
    def log_path(self) -> str:
        if not self.log_file:
            return os.path.join(self.project_path, "logs", "server.log")

        if os.path.isabs(self.log_file):
            return self.log_file

        return os.path.join(self.project_path, self.log_file)

    @cached_property
    def storage_data_path(self) -> str:
        if not self.data_path:
            return os.path.join(self.project_path, "data")

        if os.path.isabs(self.data_path):
            return self.data_path

        return os.path.join(self.project_path, self.data_path)

    @cached_property
    def mail_template_path(self) -> str:
        return os.path.join(self.server_path, "templates")

    @cached_property
    def db_migration_path(self) -> str:
        return os.path.join(self.server_path, "migrations")

    @cached_property
    def db_name(self) -> str:
        return urlparse(self.database_url).path.lstrip("/")

    @cached_property
    def computed_translations_paths(self) -> list[str]:
        paths = []

        # 1. Fastedgy built-in translations (lowest priority)
        fastedgy_translations = os.path.join(os.path.dirname(__file__), "translations")

        if os.path.exists(fastedgy_translations):
            paths.append(fastedgy_translations)

        # 2. Project translations (higher priority)
        project_translations = os.path.join(self.project_path, "translations")
        if os.path.exists(project_translations):
            paths.append(project_translations)

        # 3. Custom translations paths (highest priority)
        paths.extend(self.translations_paths)

        return paths

    @field_validator("log_format")
    def validate_log_format(cls, v):
        if isinstance(v, str) and v in [item.value for item in LogFormat]:
            return LogFormat(v)
        return v

    @field_validator("database_url")
    def validate_database_url(cls, v):
        if v:
            return v
        raise ValueError("DATABASE_URL is required")


def init_settings(env_file: str | None = None):
    if not has_service(BaseSettings):
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

        settings_class: Type[BaseSettings] = discover_settings_class()

        settings = settings_class.from_env_file(env_file)
        register_service(settings, BaseSettings)

        return settings

    return get_service(BaseSettings)


type Settings[S: BaseSettings = BaseSettings] = Annotated[S, Inject(BaseSettings)]


__all__ = [
    "BaseSettings",
    "discover_settings_class",
    "init_settings",
    "Settings",
]
