# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import importlib.util
import logging
import os
from typing import Any, Self

from babel.messages import Catalog
from babel.messages.pofile import read_po

from fastedgy.config import BaseSettings
from fastedgy.context import get_locale
from fastedgy.dependencies import Inject, get_service, has_service

logger = logging.getLogger("fastedgy.i18n")


class TranslatableString(str):
    message: str
    kwargs: dict[str, Any]

    def __new__(cls, message: str, **kwargs: Any) -> Self:
        instance = super().__new__(cls, message)
        instance.message = message
        instance.kwargs = kwargs
        return instance

    def render(self) -> str:
        from fastedgy.i18n.service import I18n

        try:
            if not has_service(BaseSettings):
                return self.message.format(**self.kwargs) if self.kwargs else self.message

            return get_service(I18n).translate(self.message, **self.kwargs)
        except Exception:
            try:
                return self.message.format(**self.kwargs) if self.kwargs else self.message
            except KeyError:
                return self.message

    def __str__(self):
        return self.render()


class I18n:
    """Service for internationalization with multi-source support."""

    def __init__(self, settings: BaseSettings = Inject(BaseSettings)):
        self.settings = settings
        self._catalogs: dict[str, dict[str, Catalog]] = {}  # {path: {locale: catalog}}
        self._loaded_locales = set()
        self._available_locales = None
        self._owners: tuple[list[str], list[tuple[str, str]]] | None = None

    def load_locale(self, locale: str) -> None:
        """Load translations for a specific locale from all sources."""
        if locale in self._loaded_locales:
            return

        application_paths, packages = self._sources()

        for translations_path in [*application_paths, *(path for _, path in packages)]:
            po_file = os.path.join(translations_path, f"{locale}.po")

            if os.path.exists(po_file):
                try:
                    with open(po_file, "rb") as f:
                        catalog = read_po(f, locale=locale)

                    if translations_path not in self._catalogs:
                        self._catalogs[translations_path] = {}

                    self._catalogs[translations_path][locale] = catalog
                except Exception as e:
                    logger.warning(f"Warning: Could not load {po_file}: {e}")

        self._loaded_locales.add(locale)

    def translate(self, message: str, **kwargs) -> str:
        """Translate a message with the catalogs of its owner, the application first, then the packages."""
        current = get_locale()
        paths, source = self._owner(message, current)

        for locale in self._locale_chain(current, source):
            translated = self._translate_in(locale, message, paths, **kwargs)

            if translated is not None:
                return translated

        try:
            return message.format(**kwargs) if kwargs else message
        except KeyError:
            return message

    def _sources(self) -> tuple[list[str], list[tuple[str, str]]]:
        if self._owners is None:
            packages = [("fastedgy", os.path.join(os.path.dirname(os.path.dirname(__file__)), "translations"))]
            packages += [
                (name, path)
                for name in self.settings.package_source_locales
                if name != "fastedgy" and (path := _translations_of(name)) is not None
            ]
            owned = {os.path.realpath(path) for _, path in packages}
            self._owners = (
                [path for path in self.settings.computed_translations_paths if os.path.realpath(path) not in owned],
                packages,
            )

        return self._owners

    def _owner(self, message: str, current: str) -> tuple[list[str], str]:
        application_paths, packages = self._sources()
        application = (application_paths, self.settings.source_locale or self.settings.fallback_locale)

        for locale in {current, self.settings.fallback_locale, *self.settings.available_locales}:
            self.load_locale(locale)

        if any(self._translates(path, message) for path in application_paths):
            return application

        for name, path in packages:
            if self._translates(path, message):
                return [path], self.settings.package_source_locales.get(name, "en")

        return application

    def _translates(self, path: str, message: str) -> bool:
        return any(
            message in catalog and bool(catalog[message].string) for catalog in self._catalogs.get(path, {}).values()
        )

    def _locale_chain(self, locale: str, source: str) -> list[str]:
        fallback = self.settings.fallback_locale

        if locale == fallback or locale.split("-")[0] == source.split("-")[0]:
            return [locale]

        return [locale, fallback]

    def _translate_in(self, locale: str, message: str, paths: list[str], **kwargs) -> str | None:
        self.load_locale(locale)

        for path in reversed(paths):
            if path in self._catalogs and locale in self._catalogs[path]:
                catalog = self._catalogs[path][locale]

                if message in catalog:
                    msg_obj = catalog[message]

                    if msg_obj.string and isinstance(msg_obj.string, (str, list)):
                        translated = msg_obj.string[0] if isinstance(msg_obj.string, list) else msg_obj.string

                        if translated and isinstance(translated, str):
                            try:
                                return translated.format(**kwargs) if kwargs else translated
                            except KeyError:
                                pass

        return None

    def get_available_locales(self) -> list[str]:
        """Get list of available locales based on existing .po files."""
        if self._available_locales is None:
            self._available_locales = self._compute_available_locales()

        return self._available_locales

    def _compute_available_locales(self) -> list[str]:
        """Compute available locales by scanning .po files."""
        available = set()
        available.add(self.settings.fallback_locale)

        for translations_path in self.settings.computed_translations_paths:
            if not os.path.exists(translations_path):
                continue

            for filename in os.listdir(translations_path):
                if filename.endswith(".po"):
                    locale = filename[:-3]
                    available.add(locale)

        return sorted(available)


def _translations_of(package: str) -> str | None:
    spec = importlib.util.find_spec(package)

    if spec is None or spec.origin is None:
        return None

    return os.path.join(os.path.dirname(spec.origin), "translations")


__all__ = [
    "I18n",
    "TranslatableString",
]
