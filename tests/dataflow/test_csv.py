# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io

from fastapi import UploadFile

from fastedgy.dataflow import decode_csv_content, detect_csv_delimiter, parse_csv_file

BANK_STATEMENT = (
    "Compte n° 12345678901;\n"
    "Solde au 07/10/2026 1 234,56 €;\n"
    "\n"
    "Date;Libellé;Débit euros;Crédit euros;\n"
    '01/09/2026;"CARTE CARREFOUR 30/08";45,30;;\n'
    '02/09/2026;"VIREMENT SALAIRE";;2 100,00;\n'
)


def _upload(content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename="data.csv")


def test_the_delimiter_is_read_from_the_content() -> None:
    assert detect_csv_delimiter(BANK_STATEMENT) == ";"
    assert detect_csv_delimiter('Date,Description,Amount\n2026-09-01,"STARBUCKS, NYC",-4.50\n') == ","
    assert detect_csv_delimiter("Date\tLabel\tAmount\n01/09/2026\tCARTE\t-45,30\n") == "\t"
    assert detect_csv_delimiter("Date|Label|Amount\n01/09/2026|CARTE|-45,30\n") == "|"


def test_a_decimal_comma_in_every_amount_does_not_take_the_place_of_the_semicolon() -> None:
    assert detect_csv_delimiter("12/09/2026;-25,00;Carte\n13/09/2026;-60,00;Prélèvement\n") == ";"


def test_a_text_without_delimiter_falls_back_to_the_comma() -> None:
    assert detect_csv_delimiter("hello\nworld\n") == ","


def test_a_file_saved_on_windows_is_read_as_cp1252() -> None:
    assert decode_csv_content("Libellé;Débit\n".encode("cp1252")) == "Libellé;Débit\n"
    assert decode_csv_content("﻿Libellé;Débit\n".encode()) == "Libellé;Débit\n"


async def test_a_csv_file_is_split_on_the_delimiter_it_uses() -> None:
    rows = await parse_csv_file(_upload(BANK_STATEMENT.encode("cp1252")))

    assert rows[3] == ["Date", "Libellé", "Débit euros", "Crédit euros", ""]
    assert rows[4][:3] == ["01/09/2026", "CARTE CARREFOUR 30/08", "45,30"]


async def test_a_given_delimiter_wins_over_the_detected_one() -> None:
    rows = await parse_csv_file(_upload(b"a;b,c\n1;2,3\n"), delimiter=",")

    assert rows == [["a;b", "c"], ["1;2", "3"]]
