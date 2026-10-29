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


async def test_a_request_writes_translations_keyed_by_locale(
    auth_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["en", "fr"], fallback_locale="en")
    french = {"Accept-Language": "fr"}

    response = await auth_http.post(
        "/api/test_courses", json={"code": "C1", "title": {"en": "Chair", "fr": "Chaise"}}, headers=french
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Chaise"

    patched = await auth_http.patch(f"/api/test_courses/{response.json()['id']}", json={"title": {"en": "Armchair"}})

    assert patched.json()["title"] == "Armchair"
    assert await read_translations(await Course.query.get(id=response.json()["id"]), "title") == {
        "en": "Armchair",
        "fr": "Chaise",
    }


async def test_a_request_refuses_translations_it_cannot_store(
    auth_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["en", "fr"], fallback_locale="en")

    unknown = await auth_http.post("/api/test_courses", json={"code": "C1", "title": {"it": "Sedia"}})
    too_long = await auth_http.post("/api/test_courses", json={"code": "C1", "title": {"fr": "x" * 41}})

    assert unknown.status_code == 422
    assert "Unavailable locale: it" in unknown.text
    assert too_long.status_code == 422
    assert await Course.query.count() == 0


async def test_the_schema_of_a_translatable_field_reads_a_string_and_writes_translations(
    auth_http: httpx.AsyncClient,
) -> None:
    schemas = (await auth_http.get("/openapi.json")).json()["components"]["schemas"]
    text = {"maxLength": 40, "type": "string"}

    assert schemas["Course"]["properties"]["title"] == {**text, "title": "Title"}
    assert schemas["Course-Create"]["properties"]["title"]["anyOf"] == [
        text,
        {
            "additionalProperties": {"anyOf": [text, {"type": "null"}]},
            "propertyNames": {"enum": ["en"]},
            "type": "object",
        },
    ]


async def test_the_translations_route_reads_every_locale_of_a_record(
    auth_http: httpx.AsyncClient, override_settings: Callable[..., None]
) -> None:
    override_settings(available_locales=["en", "fr"], fallback_locale="en")
    created = (
        await auth_http.post("/api/test_courses", json={"code": "C1", "title": {"en": "Chair", "fr": "Chaise"}})
    ).json()

    response = await auth_http.get(f"/api/test_courses/{created['id']}/translations")

    assert response.status_code == 200
    assert response.json() == {"title": {"en": "Chair", "fr": "Chaise"}, "summary": {}, "body": {}}
    assert (await auth_http.get("/api/test_courses/999999/translations")).status_code == 404


async def test_the_translations_route_is_typed_and_only_on_translatable_models(auth_http: httpx.AsyncClient) -> None:
    spec = (await auth_http.get("/openapi.json")).json()

    assert "/api/test_courses/{item_id}/translations" in spec["paths"]
    assert "/api/test_categories/{item_id}/translations" not in spec["paths"]
    assert spec["components"]["schemas"]["Course-Translations"]["properties"]["title"] == {
        "additionalProperties": {"type": "string"},
        "propertyNames": {"enum": ["en"]},
        "title": "Title",
        "type": "object",
    }

