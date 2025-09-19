# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import logging

from babel.messages import Catalog
from babel.messages.pofile import read_po

from fastedgy.config import BaseSettings
from fastedgy.context import get_locale
from fastedgy.dependencies import get_service, register_service


logger = logging.getLogger('fastedgy.i18n')


class TranslatableString(str):
    def __init__(self, message: str, **kwargs):
        self.message = message
        self.kwargs = kwargs

    def translate(self) -> str:
        from fastedgy.i18n.service import I18n

        try:
            return get_service(I18n).translate(self.message, **self.kwargs)
        except Exception:
            try:
                return self.message.format(**self.kwargs) if self.kwargs else self.message
            except KeyError:
                return self.message

    def __str__(self):
        return self.translate()


class I18n:
    """Service for internationalization with multi-source support."""

    def __init__(self, settings: BaseSettings):
        self.settings = settings
        self._catalogs: dict[str, dict[str, Catalog]] = {}  # {path: {locale: catalog}}
        self._loaded_locales = set()

    def load_locale(self, locale: str) -> None:
        """Load translations for a specific locale from all sources."""
        if locale in self._loaded_locales:
            return

        for translations_path in self.settings.computed_translations_paths:
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
        """Translate a message using current locale with priority-based lookup."""
        locale = get_locale()
        self.load_locale(locale)

        translation_paths = list(reversed(self.settings.computed_translations_paths))

        for path in translation_paths:
            if path in self._catalogs and locale in self._catalogs[path]:
                catalog = self._catalogs[path][locale]

                if message in catalog:
                    msg_obj = catalog[message]

                    if msg_obj.string and isinstance(msg_obj.string, (str, list)):
                        translated = (
                            msg_obj.string[0]
                            if isinstance(msg_obj.string, list)
                            else msg_obj.string
                        )

                        if translated and isinstance(translated, str):
                            try:
                                return (
                                    translated.format(**kwargs)
                                    if kwargs
                                    else translated
                                )
                            except KeyError:
                                # If formatting fails, fallback to original message
                                pass

        # Fallback to original message with formatting
        try:
            return message.format(**kwargs) if kwargs else message
        except KeyError:
            return message

    def get_available_locales(self) -> list[str]:
        """Get list of available locales based on existing .po files."""
        available = set()
        available.add(self.settings.fallback_locale)

        for translations_path in self.settings.computed_translations_paths:
            if not os.path.exists(translations_path):
                continue

            for filename in os.listdir(translations_path):
                if filename.endswith(".po"):
                    locale = filename[:-3]
                    available.add(locale)

        return sorted(list(available))

    def clear_cache(self) -> None:
        """Clear translation cache."""
        self._catalogs.clear()
        self._loaded_locales.clear()


register_service(lambda: I18n(get_service(BaseSettings)), I18n)


__all__ = [
    "TranslatableString",
    "I18n",
]
