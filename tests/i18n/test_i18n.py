# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.i18n import I18n, TranslatableString, _t, _ts


async def test_translate_returns_message_when_untranslated(setup_db: FastEdgy) -> None:
    assert _t("A unique untranslated sentence") == "A unique untranslated sentence"


async def test_translate_formats_keyword_arguments(setup_db: FastEdgy) -> None:
    assert _t("Hello {name}", name="World") == "Hello World"


async def test_ts_is_a_lazy_translatable_string(setup_db: FastEdgy) -> None:
    lazy = _ts("Hello {name}", name="World")

    assert isinstance(lazy, TranslatableString)
    assert str(lazy) == "Hello World"


async def test_available_locales_is_a_list(setup_db: FastEdgy) -> None:
    locales = get_service(I18n).get_available_locales()

    assert isinstance(locales, list)
