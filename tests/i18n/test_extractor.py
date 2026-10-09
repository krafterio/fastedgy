# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pathlib import Path

from babel.messages import Catalog
from babel.messages.pofile import read_po, write_po

from fastedgy.i18n.extractor import I18nExtractor


def test_post_processing_keeps_a_long_first_message(tmp_path: Path) -> None:
    long = "A sentence long enough to be wrapped over several lines, so that its msgid opens on an empty string."
    catalog = Catalog(locale="fr")
    catalog.add(long, "Une phrase assez longue pour être coupée sur plusieurs lignes.")
    catalog.add("Short", "Court")
    po_file = tmp_path / "fr.po"

    with po_file.open("wb") as f:
        write_po(f, catalog)

    I18nExtractor.__new__(I18nExtractor)._post_process_po_file(str(po_file), "fr")

    with po_file.open("rb") as f:
        ids = [message.id for message in read_po(f, locale="fr") if message.id]

    assert ids == [long, "Short"]


def _clean(tmp_path: Path, catalog: Catalog) -> str:
    po_file = tmp_path / "fr.po"

    with po_file.open("wb") as f:
        write_po(f, catalog)

    I18nExtractor.__new__(I18nExtractor)._post_process_po_file(str(po_file), "fr")

    return po_file.read_text(encoding="utf-8")


def test_post_processing_writes_the_header_once(tmp_path: Path) -> None:
    catalog = Catalog(locale="fr")
    catalog.add("Short", "Court")

    content = _clean(tmp_path, catalog)

    assert content.count('"Content-Type: ') == 1
    assert content.count('msgid "Short"') == 1
