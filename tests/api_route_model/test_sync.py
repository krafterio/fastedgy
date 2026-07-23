# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Batch sync action: transactional replay of buffered offline writes with
per-field three-way merge conflict resolution."""

import httpx

from .helpers import make_product


async def _get(client: httpx.AsyncClient, product_id: int) -> dict:
    # Plain GET: every scalar field (the shared helper narrows X-Fields).
    return (await client.get(f"/api/test_products/{product_id}")).json()


def _op(record: dict, payload: dict | None = None, op: str = "update", created_at: str | None = None) -> dict:
    return {
        "op": op,
        "id": record["id"],
        "payload": payload,
        "base": record,
        # By default the operation is enqueued "now", after any server write.
        "created_at": created_at or "2100-01-01T00:00:00Z",
    }


async def _sync(client: httpx.AsyncClient, operations: list[dict]) -> list[dict]:
    response = await client.post("/api/test_products/sync", json={"operations": operations})

    assert response.status_code == 200, response.text

    return response.json()["results"]


async def test_disjoint_fields_merge_both_writes_survive(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop", quantity=1)
    base = await _get(auth_http, product["id"])

    # Server-side write on another field after the client snapshot.
    await auth_http.patch(f"/api/test_products/{product['id']}", json={"quantity": 9})

    results = await _sync(auth_http, [_op(base, {"name": "Renamed"}, created_at="1900-01-01T00:00:00Z")])

    assert results[0]["status"] == "applied"
    fetched = await _get(auth_http, product["id"])
    assert fetched["name"] == "Renamed"
    assert fetched["quantity"] == 9


async def test_conflicting_field_lost_to_fresher_server_write(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop", quantity=1)
    base = await _get(auth_http, product["id"])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"name": "Server name"})

    # The operation was enqueued before the server write (created_at in the
    # past): the server is the last writer on 'name', 'quantity' still applies.
    results = await _sync(
        auth_http,
        [_op(base, {"name": "Client name", "quantity": 5}, created_at="1900-01-01T00:00:00Z")],
    )

    assert results[0]["status"] == "merged"
    assert results[0]["applied_fields"] == ["quantity"]
    assert results[0]["discarded_fields"] == ["name"]
    fetched = await _get(auth_http, product["id"])
    assert fetched["name"] == "Server name"
    assert fetched["quantity"] == 5


async def test_fully_conflicting_patch_reports_conflict(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"name": "Server name"})

    results = await _sync(auth_http, [_op(base, {"name": "Client name"}, created_at="1900-01-01T00:00:00Z")])

    assert results[0]["status"] == "conflict"
    assert results[0]["discarded_fields"] == ["name"]
    assert results[0]["record"]["name"] == "Server name"
    assert (await _get(auth_http, product["id"]))["name"] == "Server name"


async def test_buffered_write_wins_as_last_writer(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"name": "Server name"})

    # Enqueued after the server write: the buffered write is the last one.
    results = await _sync(auth_http, [_op(base, {"name": "Client name"})])

    assert results[0]["status"] == "applied"
    assert (await _get(auth_http, product["id"]))["name"] == "Client name"


async def test_delete_loses_to_fresher_server_write(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"name": "Still alive"})

    results = await _sync(auth_http, [_op(base, None, op="delete", created_at="1900-01-01T00:00:00Z")])

    assert results[0]["status"] == "conflict"
    assert results[0]["record"]["name"] == "Still alive"
    assert (await auth_http.get(f"/api/test_products/{product['id']}")).status_code == 200


async def test_delete_applies_as_last_writer(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    results = await _sync(auth_http, [_op(base, None, op="delete")])

    assert results[0]["status"] == "applied"
    assert (await auth_http.get(f"/api/test_products/{product['id']}")).status_code == 404


async def test_deleted_record_statuses(auth_http: httpx.AsyncClient) -> None:
    results = await _sync(
        auth_http,
        [
            {"op": "update", "id": 999999, "payload": {"name": "X"}, "base": None, "created_at": None},
            {"op": "delete", "id": 999999, "payload": None, "base": None, "created_at": None},
        ],
    )

    assert results[0]["status"] == "deleted"
    assert results[1]["status"] == "applied"  # already gone counts as done


async def test_operations_apply_in_order(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop", quantity=1)
    base = await _get(auth_http, product["id"])

    results = await _sync(
        auth_http,
        [
            _op(base, {"quantity": 2}),
            _op(base, {"quantity": 3}),
        ],
    )

    assert [result["status"] for result in results] == ["applied", "applied"]
    assert (await _get(auth_http, product["id"]))["quantity"] == 3


async def test_invalid_operation_is_rejected_alone(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    results = await _sync(
        auth_http,
        [
            _op(base, {"quantity": "not-a-number"}),
            _op(base, {"quantity": 7}),
        ],
    )

    assert results[0]["status"] == "rejected"
    assert results[0]["detail"]
    assert results[1]["status"] == "applied"
    assert (await _get(auth_http, product["id"]))["quantity"] == 7


async def test_integrity_violation_only_rejects_its_operation(auth_http: httpx.AsyncClient) -> None:
    # A NOT NULL violation aborts the operation's savepoint, not the batch.
    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    results = await _sync(
        auth_http,
        [
            _op(base, {"name": None}),
            _op(base, {"quantity": 9}),
        ],
    )

    assert results[0]["status"] == "rejected"
    assert results[1]["status"] == "applied"
    fetched = await _get(auth_http, product["id"])
    assert fetched["name"] == "Laptop"
    assert fetched["quantity"] == 9


async def test_batch_size_is_capped(auth_http: httpx.AsyncClient) -> None:
    operations = [
        {"op": "update", "id": index, "payload": {"quantity": 1}, "base": None, "created_at": None}
        for index in range(501)
    ]

    response = await auth_http.post("/api/test_products/sync", json={"operations": operations})

    assert response.status_code == 422


async def test_relation_shape_differences_do_not_conflict(auth_http: httpx.AsyncClient) -> None:
    # The client base holds the relation as an X-Fields subobject while the
    # server compares against an id-only shape: relations diff by id.
    category_a = (await auth_http.post("/api/test_categories", json={"name": "A"})).json()
    category_b = (await auth_http.post("/api/test_categories", json={"name": "B"})).json()
    product = await make_product(auth_http, name="Laptop", category=category_a["id"])

    base_response = await auth_http.get(
        f"/api/test_products/{product['id']}",
        headers={"X-Fields": "id,name,quantity,category.name"},
    )
    base = base_response.json()
    assert base["category"] == {"id": category_a["id"], "name": "A"}

    # Fresh server write on another field: without id-normalization the
    # category shape difference would flag a spurious conflict.
    await auth_http.patch(f"/api/test_products/{product['id']}", json={"quantity": 5})

    results = await _sync(
        auth_http,
        [_op(base, {"category": category_b["id"]}, created_at="1900-01-01T00:00:00Z")],
    )

    assert results[0]["status"] == "applied"
    fetched = await _get(auth_http, product["id"])
    assert fetched["category"] == {"id": category_b["id"]}


async def test_allowed_ops_align_with_the_model_route_config(auth_http: httpx.AsyncClient) -> None:
    # Tag disables the delete action: the derived sync policy rejects delete
    # operations while updates still apply.
    created = await auth_http.post("/api/test_tags", json={"name": "obsolete"})
    tag = created.json()

    denied = await auth_http.post(
        "/api/test_tags/sync",
        json={"operations": [{"op": "delete", "id": tag["id"], "payload": None, "base": None, "created_at": None}]},
    )

    assert denied.status_code == 403

    renamed = await auth_http.post(
        "/api/test_tags/sync",
        json={
            "operations": [
                {"op": "update", "id": tag["id"], "payload": {"name": "kept"}, "base": None, "created_at": None}
            ]
        },
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["results"][0]["status"] == "applied"
    assert (await auth_http.get(f"/api/test_tags/{tag['id']}")).json()["name"] == "kept"


async def test_excluded_fields_are_dropped_from_the_payload(auth_http: httpx.AsyncClient) -> None:
    from fastedgy.test.models.product import Product

    product = await make_product(auth_http, name="Laptop")
    base = await _get(auth_http, product["id"])

    results = await _sync(auth_http, [_op(base, {"name": "Renamed", "secret_code": "HACK"})])

    assert results[0]["status"] == "applied"
    assert results[0]["applied_fields"] == ["name"]
    record = await Product.query.get(id=product["id"])
    assert record.secret_code is None


async def test_relation_operations_are_never_conflicted(auth_http: httpx.AsyncClient) -> None:
    # Relation payload values are operation lists, not state: they stay out of
    # the three-way diff and always apply.
    from fastedgy.test.models.tag import Tag as TagModel

    tag = (await auth_http.post("/api/test_tags", json={"name": "urgent"})).json()
    product = await make_product(auth_http, name="Laptop")

    base_response = await auth_http.get(
        f"/api/test_products/{product['id']}",
        headers={"X-Fields": "id,name,tags.name"},
    )
    base = base_response.json()

    await auth_http.patch(f"/api/test_products/{product['id']}", json={"quantity": 3})

    results = await _sync(
        auth_http,
        [_op(base, {"tags": [["link", tag["id"]]]}, created_at="1900-01-01T00:00:00Z")],
    )

    assert results[0]["status"] == "applied"
    linked = await TagModel.query.filter(products__id=product["id"]).all()
    assert [item.id for item in linked] == [tag["id"]]
