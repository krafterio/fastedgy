# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .helpers import make_category, make_product, make_tag


async def _list(client: httpx.AsyncClient, path: str, fields: str) -> tuple[list[dict], int]:
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)

    try:
        response = await client.get(path, headers={"X-Fields": fields})
    finally:
        event.remove(Engine, "before_cursor_execute", record)

    assert response.status_code == 200, response.text

    return response.json()["items"], len(statements)


async def test_a_to_many_relation_is_read_once_for_the_whole_page(auth_http: httpx.AsyncClient) -> None:
    tags = [await make_tag(auth_http, name) for name in ("beta", "alpha")]
    await make_product(auth_http, name="First", tags=[tag["id"] for tag in tags])

    _, alone = await _list(auth_http, "/api/test_products", "name,tags.name")

    for index in range(4):
        await make_product(auth_http, name=f"Next {index}", tags=[tags[index % 2]["id"]])

    _, many = await _list(auth_http, "/api/test_products", "name,tags.name")

    assert many == alone


async def test_a_relation_of_a_relation_is_read_once_as_well(auth_http: httpx.AsyncClient) -> None:
    tags = [await make_tag(auth_http, name) for name in ("beta", "alpha")]
    fields = "name,products.name,products.tags.name"
    first = await make_category(auth_http, "Tools")
    await make_product(auth_http, name="First", category=first["id"], tags=[tags[0]["id"]])

    _, alone = await _list(auth_http, "/api/test_categories", fields)

    for index in range(4):
        another = await make_category(auth_http, f"More {index}")
        await make_product(auth_http, name=f"Next {index}", category=another["id"], tags=[tags[index % 2]["id"]])

    _, many = await _list(auth_http, "/api/test_categories", fields)

    assert many == alone


async def test_a_batched_relation_answers_what_the_item_read_answers(auth_http: httpx.AsyncClient) -> None:
    tags = [await make_tag(auth_http, name) for name in ("beta", "alpha", "gamma")]
    category = await make_category(auth_http, "Tools")
    await make_product(auth_http, name="Both", category=category["id"], tags=[tags[0]["id"], tags[1]["id"]])
    await make_product(auth_http, name="One", category=category["id"], tags=[tags[2]["id"]])
    await make_product(auth_http, name="None", category=category["id"])
    await make_category(auth_http, "Empty")

    cases = [
        ("/api/test_products", "name,tags.name"),
        ("/api/test_categories", "name,products.name,products.tags.name"),
    ]

    for path, fields in cases:
        listed, _ = await _list(auth_http, path, fields)

        assert listed

        for item in listed:
            single = await auth_http.get(f"{path}/{item['id']}", headers={"X-Fields": fields})

            assert item == single.json()
