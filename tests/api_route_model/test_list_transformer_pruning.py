# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Regression tests for the field-selector column pruning vs view transformers.

Reference behavior captured on 1.3.0 (bf062ff8, before the pruning commit):
a list request whose transformers read fields outside the X-Fields selection
triggered ZERO per-row lazy load (11.4 ms median on this scenario — all the
columns were selected). The pruning introduced in 1.3.1 (6ca5a1b) deferred
those columns and silently reloaded rows ONE BY ONE through the proxy models
(60 lazy loads, ~806 ms: N+1). Transformers must NOT have to declare anything:
the deferred columns of a pruned batch are reloaded in a single query on first
access.
"""

import statistics
import time
from typing import Any

import httpx
import pytest

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import GetViewsTransformer
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.test.models.product import Product

SEED_COUNT = 60
RUNS = 5


async def _seed_products(count: int = SEED_COUNT) -> None:
    for i in range(count):
        await Product(name=f"Product {i}", description=f"Description {i}", price="10.00", quantity=i).save()


class _ReadingTransformer(GetViewsTransformer[Product]):
    """Mimics application transformers: reads fields the client did not select."""

    async def get_views(self, request: Request, items: list[Product], ctx: dict[str, Any]) -> None:
        for item in items:
            _ = item.description
            _ = item.quantity


class _CountingLoads:
    """Counts row loads on the model AND its proxy class (pruned querysets
    build proxy instances; their deferred attribute access reloads through the
    proxy's own `load`)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch):
        self.calls = 0

        for target in {Product, Product.proxy_model}:
            original = target.load

            def make(original):
                async def counting(instance, *args, **kwargs):
                    self.calls += 1
                    return await original(instance, *args, **kwargs)

                return counting

            monkeypatch.setattr(target, "load", make(original))


def _register(transformer_cls: type) -> None:
    get_service(ViewTransformerRegistry).register_transformer(transformer_cls, Product)


def _cleanup_transformers() -> None:
    ViewTransformerRegistry._transformers.pop(Product, None)


@pytest.fixture(autouse=True)
def _isolated_registry():
    _cleanup_transformers()
    yield
    _cleanup_transformers()


async def _timed_list(client: httpx.AsyncClient, runs: int = RUNS) -> tuple[dict, float]:
    payload: dict = {}
    times: list[float] = []

    for _ in range(runs):
        start = time.perf_counter()
        response = await client.get(f"/api/test_products?limit={SEED_COUNT + 10}", headers={"X-Fields": "id,name"})
        times.append((time.perf_counter() - start) * 1000)
        assert response.status_code == 200, response.text
        payload = response.json()

    return payload, statistics.median(times)


async def test_transformer_reading_unselected_fields_does_not_n_plus_one(
    auth_http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1.3.0 reference: no per-row reload whatever the transformers read.

    With pruning, at most ONE batched reload per request is allowed — never
    one per instance."""
    await _seed_products()
    _register(_ReadingTransformer)
    counter = _CountingLoads(monkeypatch)

    payload, median_ms = await _timed_list(auth_http)

    assert len(payload["items"]) == SEED_COUNT
    print(f"\n[unselected reads] median {median_ms:.1f} ms, load() calls/run: {counter.calls / RUNS:.1f}")
    assert counter.calls <= RUNS  # <= 1 per request (0 on 1.3.0, 1 batched reload with pruning)


async def test_pruning_stays_active_while_transformers_read_anything(auth_http: httpx.AsyncClient) -> None:
    """The response keeps only the selected fields: the batch reload hydrates
    the instances for the transformers without leaking columns to the client."""
    pytest.importorskip("fastedgy.orm.deferred_batch")

    await _seed_products()
    _register(_ReadingTransformer)

    payload, _ = await _timed_list(auth_http, runs=1)

    assert set(payload["items"][0].keys()) <= {"id", "name"}


async def test_transformer_reads_correct_values_from_batched_reload(auth_http: httpx.AsyncClient) -> None:
    class _CollectingTransformer(GetViewsTransformer[Product]):
        collected: dict[str, tuple[str | None, int]] = {}

        async def get_views(self, request: Request, items: list[Product], ctx: dict[str, Any]) -> None:
            for item in items:
                type(self).collected[item.name] = (item.description, item.quantity)

    await _seed_products()
    _register(_CollectingTransformer)

    payload, _ = await _timed_list(auth_http, runs=1)

    assert len(payload["items"]) == SEED_COUNT
    assert _CollectingTransformer.collected["Product 3"] == ("Description 3", 3)
    assert _CollectingTransformer.collected["Product 59"] == ("Description 59", 59)
