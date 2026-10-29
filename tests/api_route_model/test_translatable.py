# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from collections.abc import Callable

import httpx

from fastedgy.orm.fields import read_translations
from fastedgy.test.models.course import Course


async def test_a_request_reads_and_writes_in_its_language(
    auth_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["en", "fr"], fallback_locale="en")
    french = {"Accept-Language": "fr-FR,fr;q=0.9"}

    created = (await auth_http.post("/api/test_courses", json={"code": "C1", "title": "Chair"})).json()
    response = await auth_http.patch(f"/api/test_courses/{created['id']}", json={"title": "Chaise"}, headers=french)

    assert response.status_code == 200
    assert response.json()["title"] == "Chaise"
    assert (await auth_http.get(f"/api/test_courses/{created['id']}", headers=french)).json()["title"] == "Chaise"
    assert (await auth_http.get(f"/api/test_courses/{created['id']}")).json()["title"] == "Chair"

    listed = (await auth_http.get("/api/test_courses?order_by=title", headers=french)).json()

    assert [item["title"] for item in listed["items"]] == ["Chaise"]
    assert await read_translations(await Course.query.get(id=created["id"]), "title") == {
        "en": "Chair",
        "fr": "Chaise",
    }


async def test_the_schema_of_a_translatable_field_is_a_string(auth_http: httpx.AsyncClient) -> None:
    schemas = (await auth_http.get("/openapi.json")).json()["components"]["schemas"]
    title = next(schema for name, schema in schemas.items() if name.startswith("Course"))["properties"]["title"]

    assert title["type"] == "string"
    assert title["maxLength"] == 40
