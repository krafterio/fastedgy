# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

from babel.messages import Catalog
from babel.messages.pofile import read_po

from fastedgy.config import BaseSettings
from fastedgy.context import get_locale
from fastedgy.dependencies import get_service, register_service


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
                    with open(po_file, 'rb') as f:
                        catalog = read_po(f, locale=locale)

                    if translations_path not in self._catalogs:
                        self._catalogs[translations_path] = {}

                    self._catalogs[translations_path][locale] = catalog
                except Exception as e:
                    # Log error but continue with other sources
                    print(f"Warning: Could not load {po_file}: {e}")

        self._loaded_locales.add(locale)

    def _(self, message: str, **kwargs) -> str:
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
                        translated = msg_obj.string[0] if isinstance(msg_obj.string, list) else msg_obj.string

                        if translated and isinstance(translated, str):
                            try:
                                return translated.format(**kwargs) if kwargs else translated
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

        for translations_path in self.settings.computed_translations_paths:
            if not os.path.exists(translations_path):
                continue

            for filename in os.listdir(translations_path):
                if filename.endswith('.po'):
                    locale = filename[:-3]
                    available.add(locale)

        return sorted(list(available))

    def clear_cache(self) -> None:
        """Clear translation cache."""
        self._catalogs.clear()
        self._loaded_locales.clear()


register_service(lambda: I18n(get_service(BaseSettings)), I18n)


__all__ = [
    "I18n",
]
