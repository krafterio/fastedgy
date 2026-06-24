# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx


async def make_category(client: httpx.AsyncClient, name: str = "Books", **extra) -> dict:
    return (await client.post("/api/test_categories", json={"name": name, **extra})).json()


async def make_tag(client: httpx.AsyncClient, name: str) -> dict:
    return (await client.post("/api/test_tags", json={"name": name})).json()


async def make_product(client: httpx.AsyncClient, **extra) -> dict:
    payload = {"name": "Laptop", "price": "999.00", **extra}
    return (await client.post("/api/test_products", json=payload)).json()


async def get_product(client: httpx.AsyncClient, product_id: int) -> dict:
    # Relations are excluded from the default payload; request them explicitly.
    response = await client.get(
        f"/api/test_products/{product_id}",
        headers={"X-Fields": "name,category.name,tags.name"},
    )
    return response.json()


def tag_ids(product: dict) -> set[int]:
    return {tag["id"] for tag in (product.get("tags") or [])}


async def seed_user(email: str = "john@example.io", name: str | None = "John Doe", password: str = "secret"):
    # Users are created through a dedicated flow, not the generic CRUD endpoint
    # (``password`` is excluded from the input model), so seed them via the ORM.
    from fastedgy.test.models.user import User

    user = User(email=email, name=name, password=password)
    await user.save()

    return user

