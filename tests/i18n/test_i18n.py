# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
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


async def test_translate_formats_keyword_arguments(setup_db: FastEdgy) -> None:
    assert _t("Hello {name}", name="World") == "Hello World"


async def test_ts_is_a_lazy_translatable_string(setup_db: FastEdgy) -> None:
    lazy = _ts("Hello {name}", name="World")

    assert isinstance(lazy, TranslatableString)
    assert str(lazy) == "Hello World"


async def test_available_locales_is_a_list(setup_db: FastEdgy) -> None:
    locales = get_service(I18n).get_available_locales()

    assert isinstance(locales, list)
