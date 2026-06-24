# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def test_metadatas_describe_registered_models(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.get("/api/dataset/metadatas")

    assert response.status_code == 200

    data = response.json()

    assert "product" in data

    product = data["product"]

    assert product["api_name"] == "test_products"
    assert product["searchable"] is True
    assert product["search_field"] == "search_value"
    assert "name" in product["fields"]


async def test_metadatas_require_authentication(setup_http: httpx.AsyncClient) -> None:
    assert (await setup_http.get("/api/dataset/metadatas")).status_code == 401


async def test_resequence_unknown_model_is_rejected(auth_http: httpx.AsyncClient) -> None:
    response = await auth_http.put(
        "/api/dataset/resequence",
        json={"model_name": "does_not_exist", "sequence_field": "sequence", "ids": [1]},
    )

    assert response.status_code == 400
