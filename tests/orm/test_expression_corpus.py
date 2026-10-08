# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The expression corpus the query builder of vue-fastedgy is held to.

vue-fastedgy checks that writing back a parsed input gives its output. Here,
each input and its output must read the same rows: what the builder writes is
accepted by the server, and read as the expression it came from.
"""

import json
from pathlib import Path
from typing import Any

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import filter_query

CORPUS_PATH = Path(__file__).parent / "fixtures/expressions.json"


async def _ids(expression: Any) -> list[int]:
    from fastedgy.test.models.product import Product

    query = filter_query(Product.query.get_queryset(), json.dumps(expression))

    return sorted(item.id for item in await query.all())


async def test_each_output_reads_the_rows_of_its_input(setup_db: FastEdgy) -> None:
    from tests.orm.test_filter_parity import _seed

    await _seed()

    for case in json.loads(CORPUS_PATH.read_text())["cases"]:
        if case["input"] in (None, []):
            assert case["output"] is None, case["name"]
            continue

        assert await _ids(case["input"]) == await _ids(case["output"]), case["name"]
