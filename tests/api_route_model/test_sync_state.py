# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Sync state route: what each replicated model holds, in one request.

An offline client walks a manifest to mirror a model, a request per page even
when nothing moved. This answers the same question for every model at once, so
a client whose own numbers match can skip the walk entirely.
"""

import httpx

from .helpers import make_product, make_tag


async def _state(client: httpx.AsyncClient, models: str | None = None) -> dict[str, dict]:
    response = await client.get("/api/dataset/sync-state", params={"models": models} if models else None)

    assert response.status_code == 200, response.text

    return {item["model"]: item for item in response.json()["items"]}


async def test_lists_the_replicated_models_with_their_regime(auth_http: httpx.AsyncClient) -> None:
    items = await _state(auth_http)

    assert items["product"]["mode"] == "full"
    assert items["ticket"]["mode"] == "partial"
    # Synced through custom routes: the Meta override declares it too.
    assert items["comment"]["mode"] == "full"
    assert "category" not in items, "a model nobody replicates has nothing to say here"


async def test_counts_and_dates_what_the_caller_can_read(auth_http: httpx.AsyncClient) -> None:
    assert (await _state(auth_http, "product"))["product"] == {
        "model": "product",
        "mode": "full",
        "count": 0,
        "updated_at": None,
    }

    await make_product(auth_http, name="Laptop")
    fresh = await make_product(auth_http, name="Keyboard")

    state = (await _state(auth_http, "product"))["product"]
    stored = (await auth_http.get(f"/api/test_products/{fresh['id']}")).json()

    assert state["count"] == 2
    assert state["updated_at"] == stored["updated_at"]


async def test_a_write_moves_the_date_a_delete_moves_the_count(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop")
    other = await make_product(auth_http, name="Keyboard")
    before = (await _state(auth_http, "product"))["product"]

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"quantity": 9})
    after_write = (await _state(auth_http, "product"))["product"]

    assert after_write["count"] == before["count"]
    assert after_write["updated_at"] > before["updated_at"]

    await auth_http.delete(f"/api/test_products/{other['id']}")

    assert (await _state(auth_http, "product"))["product"]["count"] == before["count"] - 1


async def test_narrows_to_the_requested_models(auth_http: httpx.AsyncClient) -> None:
    await make_tag(auth_http, "Sale")

    items = await _state(auth_http, "tag,product")

    assert set(items) == {"tag", "product"}
    assert items["tag"]["count"] == 1
