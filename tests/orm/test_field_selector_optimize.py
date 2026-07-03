# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import httpx

from fastedgy.app import FastEdgy
from fastedgy.orm.field_selector import (
    apply_field_map_optimizations,
    filter_selected_fields,
    optimize_query_filter_fields,
    parse_field_selector_input,
)
from fastedgy.orm.query import QuerySet
from fastedgy.test.models.fs_optimize import FsoBrand, FsoCategory, FsoProduct, FsoTag

from tests.api_route_model.helpers import make_category, make_product, make_tag


async def _sql(query: QuerySet) -> str:
    return str(await query.as_select())


def _select_part(sql: str) -> str:
    return sql.split("FROM")[0]


async def _create_product_graph() -> FsoProduct:
    brand = await FsoBrand.query.create(name="Acme", motto="Boom", rank=3)
    category = await FsoCategory.query.create(name="Tools", summary="Hardware", brand=brand)

    return await FsoProduct.query.create(
        name="Hammer",
        sku="HAM-1",
        price=10.0,
        quantity=4,
        internal_note="fragile",
        category=category,
    )


async def test_deep_to_one_joins_and_prunes_columns(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,category.brand.name")
    sql = await _sql(query)

    assert sql.count("JOIN") == 2
    assert "test_fso_categories" in sql
    assert "test_fso_brands" in sql
    assert "DISTINCT" not in sql

    select_part = _select_part(sql)
    assert "test_fso_products.name" in select_part
    assert "sku" not in select_part
    assert "summary" not in select_part
    assert "motto" not in select_part
    assert "rank" not in select_part


async def test_pk_only_fk_keeps_column_without_join(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,category")
    sql = await _sql(query)

    assert "JOIN" not in sql

    select_part = _select_part(sql)
    assert "category" in select_part
    assert "sku" not in select_part


async def test_to_many_relation_is_not_joined(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,tags.name")
    sql = await _sql(query)

    assert "JOIN" not in sql
    assert "test_fso_tags" not in sql
    assert "DISTINCT" not in sql


async def test_computed_field_deps_are_selected(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "stock_value")
    sql = await _sql(query)

    select_part = _select_part(sql)
    assert "price" in select_part
    assert "quantity" in select_part
    assert "sku" not in select_part


async def test_computed_field_relation_deps_join_and_prune(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "brand_name")
    sql = await _sql(query)

    assert sql.count("JOIN") == 2

    select_part = _select_part(sql)
    assert "name" in select_part
    assert "motto" not in select_part
    assert "summary" not in select_part
    assert "sku" not in select_part


async def test_computed_field_without_deps_disables_level_pruning(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "display_label")
    sql = await _sql(query)

    select_part = _select_part(sql)
    assert "sku" in select_part
    assert "quantity" in select_part
    assert "price" in select_part


async def test_prune_columns_false_keeps_all_columns(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,category.brand.name", prune_columns=False)
    sql = await _sql(query)

    assert sql.count("JOIN") == 2

    select_part = _select_part(sql)
    assert "sku" in select_part
    assert "summary" in select_part
    assert "motto" in select_part


async def test_wildcard_keeps_all_root_columns(setup_db: FastEdgy) -> None:
    query = optimize_query_filter_fields(FsoProduct.query.all(), "+")
    sql = await _sql(query)

    select_part = _select_part(sql)
    assert "sku" in select_part
    assert "category" in select_part

    assert sql.count("JOIN") == 2
    assert "motto" not in select_part


async def test_deep_chain_response_shape(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()

    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,category.brand.name")
    item = await query.filter(id=product.id).get()
    dump = await filter_selected_fields(item, "name,category.brand.name")

    assert dump == {
        "id": product.id,
        "name": "Hammer",
        "category": {
            "id": item.category.id,
            "brand": {
                "id": item.category.brand.id,
                "name": "Acme",
            },
        },
    }


async def test_null_to_one_relation_emits_none(setup_db: FastEdgy) -> None:
    product = await FsoProduct.query.create(name="Loose", price=1.0)

    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,category.brand.name")
    item = await query.filter(id=product.id).get()
    dump = await filter_selected_fields(item, "name,category.brand.name")

    assert dump == {"id": product.id, "name": "Loose", "category": None}


async def test_pk_only_fk_serialization(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()

    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,category")
    item = await query.filter(id=product.id).get()
    dump = await filter_selected_fields(item, "name,category")

    assert dump["category"] == {"id": (await FsoCategory.query.get()).id}


async def test_to_many_serialization_is_pruned_and_ordered(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()
    tag_b = await FsoTag.query.create(name="beta", color="blue")
    tag_a = await FsoTag.query.create(name="alpha", color="red")
    await product.tags.add(tag_b)
    await product.tags.add(tag_a)

    query = optimize_query_filter_fields(FsoProduct.query.all(), "name,tags.name")
    item = await query.filter(id=product.id).get()
    dump = await filter_selected_fields(item, "name,tags.name")

    assert dump["tags"] == [
        {"id": tag_a.id, "name": "alpha"},
        {"id": tag_b.id, "name": "beta"},
    ]


async def test_to_many_subquery_is_pruned_through_embed(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()
    await product.tags.add(await FsoTag.query.create(name="promo", color="red"))

    item = await FsoProduct.query.get(id=product.id)
    subquery = apply_field_map_optimizations(item.tags.limit(1000).all(), {"id": True, "name": True})
    sql = await _sql(subquery)

    assert "name" in sql
    assert "color" not in sql
    assert "created_at" not in sql


async def test_computed_values_survive_pruning(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()

    query = optimize_query_filter_fields(FsoProduct.query.all(), "stock_value,brand_name,display_label")
    item = await query.filter(id=product.id).get()
    dump = await filter_selected_fields(item, "stock_value,brand_name,display_label")

    assert dump == {
        "id": product.id,
        "stock_value": 40.0,
        "brand_name": "Acme",
        "display_label": "Hammer x4",
    }


async def test_excluded_field_stays_out_of_wildcard_response(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()

    query = optimize_query_filter_fields(FsoProduct.query.all(), "+")
    item = await query.filter(id=product.id).get()
    dump = await filter_selected_fields(item, "+")

    assert "internal_note" not in dump
    assert dump["name"] == "Hammer"


async def test_optimized_query_matches_unoptimized_response(setup_db: FastEdgy) -> None:
    product = await _create_product_graph()
    fields_expr = "name,sku,stock_value,category.name,category.brand.name"

    optimized = await optimize_query_filter_fields(FsoProduct.query.all(), fields_expr).filter(id=product.id).get()
    plain = await FsoProduct.query.filter(id=product.id).get()

    assert await filter_selected_fields(optimized, fields_expr) == await filter_selected_fields(plain, fields_expr)


async def test_apply_field_map_optimizations_from_parsed_map(setup_db: FastEdgy) -> None:
    map_fields = parse_field_selector_input(FsoProduct, "name,category.brand.name")
    assert map_fields is not None

    query = apply_field_map_optimizations(FsoProduct.query.all(), map_fields)
    sql = await _sql(query)

    assert sql.count("JOIN") == 2
    assert "sku" not in _select_part(sql)


async def test_list_endpoint_with_x_fields(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Tools")
    tag = await make_tag(auth_http, "promo")
    product = await make_product(auth_http, name="Hammer", category=category["id"], tags=[tag["id"]])

    response = await auth_http.get(
        "/api/test_products",
        headers={"X-Fields": "name,category.name,tags.name"},
    )
    assert response.status_code == 200

    item = next(entry for entry in response.json()["items"] if entry["id"] == product["id"])
    assert item == {
        "id": product["id"],
        "name": "Hammer",
        "category": {"id": category["id"], "name": "Tools"},
        "tags": [{"id": tag["id"], "name": "promo"}],
    }


async def test_get_endpoint_with_x_fields(auth_http: httpx.AsyncClient) -> None:
    category = await make_category(auth_http, "Tools")
    product = await make_product(auth_http, name="Hammer", category=category["id"])

    response = await auth_http.get(
        f"/api/test_products/{product['id']}",
        headers={"X-Fields": "name,category.name"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": product["id"],
        "name": "Hammer",
        "category": {"id": category["id"], "name": "Tools"},
    }


async def test_patch_endpoint_saves_fully_and_filters_response(auth_http: httpx.AsyncClient) -> None:
    product = await make_product(auth_http, name="Hammer", description="Steel head", quantity=1)

    response = await auth_http.patch(
        f"/api/test_products/{product['id']}",
        json={"quantity": 7},
        headers={"X-Fields": "name,quantity"},
    )
    assert response.status_code == 200
    assert response.json() == {"id": product["id"], "name": "Hammer", "quantity": 7}

    from fastedgy.test.models.product import Product

    reloaded = await Product.query.get(id=product["id"])
    assert reloaded.quantity == 7
    assert reloaded.description == "Steel head"
