# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os

import re

import importlib.util

import site

from dataclasses import dataclass, field

from datetime import datetime

from typing import Set

from babel.messages import Catalog
from babel.messages.pofile import write_po, read_po

from fastedgy.config import BaseSettings
from fastedgy import context


@dataclass
class ExtractorResult:
    """Result object for extraction operations."""

    success: bool
    message: str = ""
    error: str = ""
    files_created: list[str] = field(default_factory=list)
    files_updated: list[str] = field(default_factory=list)
    strings_found: int = 0
    strings_added: int = 0


class I18nExtractor:
    """Service for extracting and managing translation files."""

    def __init__(self, settings: BaseSettings):
        self.settings = settings

    def init(self, locale: str, package: str | None = None) -> ExtractorResult:
        """Initialize a new locale by creating a .po file with all translatable strings."""
        try:
            scan_path, translations_dir = self._resolve_package_paths(package)
            messages = self._extract_messages(scan_path)
            os.makedirs(translations_dir, exist_ok=True)
            po_file = os.path.join(translations_dir, f"{locale}.po")

            if os.path.exists(po_file):
                pkg_info = f" for package '{package}'" if package else ""
                return ExtractorResult(
                    success=False,
                    error=f"Translation file for locale '{locale}' already exists{pkg_info}: {po_file}. Use 'extract' to update existing translations.",
                )

            catalog = self._create_catalog(locale)

            for message in messages:
                catalog.add(message)

            with open(po_file, "wb") as f:
                write_po(f, catalog, sort_by_file=True, ignore_obsolete=True)

            self._post_process_po_file(po_file, locale)

            pkg_info = f" for package '{package}'" if package else ""

            return ExtractorResult(
                success=True,
                message=f"Created {po_file} with {len(messages)} strings to translate{pkg_info}",
                files_created=[po_file],
                strings_found=len(messages),
            )

        except FileNotFoundError as e:
            return ExtractorResult(success=False, error=str(e))
        except Exception as e:
            return ExtractorResult(success=False, error=f"Unexpected error: {e}")

    def extract(
        self, locale: str | None = None, package: str | None = None
    ) -> ExtractorResult:
        """Extract translatable strings and update .po files."""
        try:
            scan_path, translations_dir = self._resolve_package_paths(package)

            if locale:
                locales = [locale]
            else:
                if not os.path.exists(translations_dir):
                    pkg_info = f" for package '{package}'" if package else ""

                    return ExtractorResult(
                        success=False,
                        error=f"No translations directory found{pkg_info}. Run 'init' first.",
                    )

                locales = []

                for filename in os.listdir(translations_dir):
                    if filename.endswith(".po"):
                        locales.append(filename[:-3])

                if not locales:
                    pkg_info = f" for package '{package}'" if package else ""

                    return ExtractorResult(
                        success=False,
                        error=f"No .po files found{pkg_info}. Run 'init <locale>' first.",
                    )

            messages = self._extract_messages(scan_path)
            files_updated = []
            total_added = 0

            for loc in locales:
                po_file = os.path.join(translations_dir, f"{loc}.po")

                if os.path.exists(po_file):
                    with open(po_file, "rb") as f:
                        catalog = read_po(f, locale=loc)

                    catalog.revision_date = datetime.now(context.get_timezone())
                else:
                    catalog = self._create_catalog(loc)

                added_count = 0

                for message in messages:
                    if not catalog.get(message):
                        catalog.add(message)
                        added_count += 1

                with open(po_file, "wb") as f:
                    write_po(f, catalog, sort_by_file=True, ignore_obsolete=True)

                self._post_process_po_file(po_file, loc)

                files_updated.append(po_file)
                total_added += added_count

            pkg_info = f" for package '{package}'" if package else ""
            result_message = (
                f"Updated {len(locales)} locale(s){pkg_info}: {', '.join(locales)}"
            )

            if total_added > 0:
                result_message += f" (+{total_added} new strings)"

            return ExtractorResult(
                success=True,
                message=result_message,
                files_updated=files_updated,
                strings_found=len(messages),
                strings_added=total_added,
            )

        except FileNotFoundError as e:
            return ExtractorResult(success=False, error=str(e))
        except Exception as e:
            return ExtractorResult(success=False, error=f"Unexpected error: {e}")

    def _resolve_package_paths(self, package: str | None) -> tuple[str, str]:
        """
        Resolve scan path and translations directory based on package option.

        Returns:
            tuple[str, str]: (scan_path, translations_dir)
        """
        if not package:
            # Default: use project paths
            return self.settings.server_path, os.path.join(
                self.settings.project_path, "translations"
            )

        # Try to import the package to get its path
        try:
            spec = importlib.util.find_spec(package)

            if spec and spec.origin:
                if spec.origin.endswith("__init__.py"):
                    package_path = os.path.dirname(spec.origin)
                else:
                    package_path = os.path.dirname(spec.origin)

                translations_dir = os.path.join(package_path, "translations")

                return package_path, translations_dir
        except (ImportError, ModuleNotFoundError):
            pass

        # Look in site-packages
        for site_packages in site.getsitepackages():
            package_path = os.path.join(site_packages, package)

            if os.path.exists(package_path):
                translations_dir = os.path.join(package_path, "translations")

                return package_path, translations_dir

        # Try relative to project root
        package_path = os.path.join(self.settings.project_path, package)

        if os.path.exists(package_path):
            translations_dir = os.path.join(package_path, "translations")

            return package_path, translations_dir

        raise FileNotFoundError(
            f"Package '{package}' not found. Check the package name and ensure it's installed or available."
        )

    def _extract_messages(self, server_path: str) -> Set[str]:
        """Extract translatable messages from Python files."""
        messages = set()

        # Pattern for _ts(), _t() or _() function calls
        patterns = [
            r'_ts\s*\(\s*["\']([^"\']+)["\']\s*[,\)]',
            r'_t\s*\(\s*["\']([^"\']+)["\']\s*[,\)]',
            r'_\s*\(\s*["\']([^"\']+)["\']\s*[,\)]',
        ]

        for root, dirs, files in os.walk(server_path):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__"))]

            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()

                        for pattern in patterns:
                            matches = re.findall(pattern, content)
                            messages.update(matches)

                    except Exception:
                        continue

        return messages

    def _create_catalog(self, locale: str) -> Catalog:
        """Create a new catalog with clean headers."""
        now = datetime.now(context.get_timezone())
        catalog = Catalog(
            locale=locale,
            creation_date=now,
            revision_date=now,
        )
        catalog.header_comment = f"# {locale.upper()} translations"

        return catalog

    def _post_process_po_file(self, po_file: str, locale: str) -> None:
        """Post-process .po file to clean headers manually."""
        plural_forms = {
            "en": "nplurals=2; plural=(n != 1);",
            "fr": "nplurals=2; plural=(n > 1);",
            "es": "nplurals=2; plural=(n != 1);",
            "de": "nplurals=2; plural=(n != 1);",
            "it": "nplurals=2; plural=(n != 1);",
            "pt": "nplurals=2; plural=(n != 1);",
            "ru": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);",
            "ja": "nplurals=1; plural=0;",
            "zh": "nplurals=1; plural=0;",
            "ar": "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 && n%100<=99 ? 4 : 5);",
        }

        with open(po_file, "r", encoding="utf-8") as f:
            content = f.read()

        pot_creation_match = re.search(r'"POT-Creation-Date: ([^"]+)"', content)
        po_revision_match = re.search(r'"PO-Revision-Date: ([^"]+)"', content)

        pot_creation_date = pot_creation_match.group(1) if pot_creation_match else None
        po_revision_date = po_revision_match.group(1) if po_revision_match else None

        first_msg_match = re.search(r'\n\n((?:#[^\n]*\n)*msgid "[^"])', content)

        if first_msg_match:
            first_msg_start = content.find(first_msg_match.group(1))
            messages_part = content[first_msg_start:]

            clean_content = f"""# {locale.upper()} translations
#, fuzzy
msgid ""
msgstr ""
"""

            if pot_creation_date:
                clean_content += f'"POT-Creation-Date: {pot_creation_date}\\n"\n'
            if po_revision_date:
                clean_content += f'"PO-Revision-Date: {po_revision_date}\\n"\n'

            clean_content += f'"Content-Type: text/plain; charset=utf-8\\n"\n'
            clean_content += f'"Language: {locale}\\n"\n'
            clean_content += (
                f'"{plural_forms.get(locale, "nplurals=2; plural=(n != 1);")}\\n"\n'
            )
            clean_content += "\n"
            clean_content += messages_part

            with open(po_file, "w", encoding="utf-8") as f:
                f.write(clean_content)
