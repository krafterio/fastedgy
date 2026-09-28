# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable
from pathlib import Path

import pytest

from fastedgy.app import FastEdgy
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.i18n import I18n, TranslatableString, _t, _ts
from fastedgy.test.factories import use_request


async def test_translate_returns_message_when_untranslated(setup_db: FastEdgy) -> None:
    assert _t("A unique untranslated sentence") == "A unique untranslated sentence"


async def test_renders_french_labels_and_parametrized_messages(setup_db: FastEdgy) -> None:
    with use_request(locale="fr"):
        # model label
        assert _t("User") == "Utilisateur"

        # short message with a parameter
        assert _t("Model {model_name} not found", model_name="Product") == "Modèle Product introuvable"

        # parameter embedded mid-sentence
        assert _t("Unsupported format: {format}", format="pdf") == "Format non pris en charge : pdf"

        # long sentence
        assert _t("The resource is currently being used by another operation. Please try again in a few moments.") == (
            "La ressource est actuellement utilisée par une autre opération. Veuillez réessayer dans quelques instants."
        )


async def test_a_missing_translation_is_looked_up_in_the_fallback_locale(
    setup_db: FastEdgy, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["fr", "es"], fallback_locale="fr")

    with use_request(locale="es"):
        assert _t("User") == "Utilisateur"


async def test_a_message_of_fastedgy_is_its_own_text_in_english_whatever_the_fallback(
    setup_db: FastEdgy, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["en", "fr"], fallback_locale="fr")

    with use_request(locale="en"):
        assert _t("User") == "User"


async def test_a_message_the_application_translates_never_takes_the_word_of_a_package(
    setup_db: FastEdgy, override_settings: Callable[..., None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "en.po").write_text('msgid ""\nmsgstr ""\n\nmsgid "User"\nmsgstr "Member"\n', encoding="utf-8")
    override_settings(
        available_locales=["fr", "en"], fallback_locale="en", source_locale="fr", translations_paths=[str(tmp_path)]
    )
    settings = get_service(BaseSettings)
    monkeypatch.delitem(settings.__dict__, "computed_translations_paths", raising=False)
    i18n = I18n(settings)

    with use_request(locale="fr"):
        assert i18n.translate("User") == "User"

    with use_request(locale="en"):
        assert i18n.translate("User") == "Member"


async def test_a_package_keeps_the_source_language_the_application_gives_it(
    setup_db: FastEdgy, override_settings: Callable[..., None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    translations = tmp_path / "germanpkg" / "translations"
    translations.mkdir(parents=True)
    (tmp_path / "germanpkg" / "__init__.py").write_text("", encoding="utf-8")
    (translations / "en.po").write_text('msgid ""\nmsgstr ""\n\nmsgid "Teilen"\nmsgstr "Share"\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    override_settings(available_locales=["de", "en"], fallback_locale="en", package_source_locales={"germanpkg": "de"})
    i18n = I18n(get_service(BaseSettings))

    with use_request(locale="en"):
        assert i18n.translate("Teilen") == "Share"

    with use_request(locale="de"):
        assert i18n.translate("Teilen") == "Teilen"


async def test_translate_formats_keyword_arguments(setup_db: FastEdgy) -> None:
    assert _t("Hello {name}", name="World") == "Hello World"


async def test_ts_is_a_lazy_translatable_string(setup_db: FastEdgy) -> None:
    lazy = _ts("Hello {name}", name="World")

    assert isinstance(lazy, TranslatableString)
    assert str(lazy) == "Hello World"


async def test_available_locales_is_a_list(setup_db: FastEdgy) -> None:
    locales = get_service(I18n).get_available_locales()

    assert isinstance(locales, list)
