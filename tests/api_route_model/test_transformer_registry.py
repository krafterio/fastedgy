# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Which view transformers a read runs."""

from typing import Any

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import GetViewTransformer
from fastedgy.http import Request
from fastedgy.test.models.category import Category


class _ForOneRead(GetViewTransformer[Category]):
    """Passed to a single read, registered nowhere."""

    async def get_view(
        self, request: Request, item: Category, item_dump: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        return item_dump


def test_a_transformer_passed_to_a_read_runs_once() -> None:
    found = ViewTransformerRegistry().get_transformers(GetViewTransformer, Category, [_ForOneRead])

    assert len([transformer for transformer in found if isinstance(transformer, _ForOneRead)]) == 1
