# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import HTTPException

from fastedgy import context
from fastedgy.api_route_model.action.generators import (
    generate_input_create_model,
    generate_input_patch_model,
)
from fastedgy.api_route_model.actions.create_action import create_item_action
from fastedgy.api_route_model.actions.patch_action import patch_item_action
from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.depends.security import get_current_workspace
from fastedgy.http import Request
from fastedgy.metadata_model import MetadataModelRegistry
from fastedgy.models.extra_field_model import WorkspaceExtraFieldModel
from fastedgy.models.workspace_extra_field import WorkspaceExtraFieldType
from fastedgy.orm.extra_fields import load_workspace_extra_fields
from fastedgy.orm.field_selector import filter_selected_fields
from fastedgy.orm.filter.builder import filter_query
from fastedgy.orm.order_by import inject_order_by, parse_order_by
from fastedgy.test.factories import create_user, create_workspace, use_request
from fastedgy.test.models.product import Product
from fastedgy.test.models.workspace_extra_field import WorkspaceExtraField
from fastedgy.test.models.workspace_user import WorkspaceUser


def _extra_field(name: str, field_type: WorkspaceExtraFieldType) -> WorkspaceExtraField:
    return WorkspaceExtraField(
        label=name.title(),
        name=name,
        field_type=field_type,
        model=WorkspaceExtraFieldModel.product,
        required=False,
    )


def _declare_extra_fields() -> None:
    context.set_workspace_extra_fields(
        [
            _extra_field("priority", WorkspaceExtraFieldType.integer),
            _extra_field("owner", WorkspaceExtraFieldType.char),
        ]
    )


async def _create_products() -> None:
    await Product.query.create(name="Alpha", price=Decimal("1.00"), extra={"priority": 2, "owner": "ada"})
    await Product.query.create(name="Beta", price=Decimal("2.00"), extra={"priority": 1, "owner": "grace"})
    await Product.query.create(name="Gamma", price=Decimal("3.00"), extra=None)


async def test_context_keeps_every_extra_field_of_a_model(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()

        assert sorted(context.get_map_workspace_extra_fields("product")) == ["owner", "priority"]


async def test_order_by_accepts_a_declared_extra_field(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()

        assert parse_order_by(Product, "extra_priority:desc") == [("extra_priority", "desc")]


async def test_order_by_drops_an_undeclared_extra_field(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()

        assert parse_order_by(Product, "extra_unknown") == []


async def test_order_by_sorts_on_the_extra_field_value(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        query = inject_order_by(Product.query.get_queryset(), "extra_priority")
        names = [product.name for product in await query.all()]

        assert names[:2] == ["Beta", "Alpha"]


async def test_filter_matches_on_the_extra_field_value(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        query = filter_query(Product.query.get_queryset(), json.dumps(["extra_owner", "=", "ada"]))

        assert [product.name for product in await query.all()] == ["Alpha"]


async def test_selection_returns_the_extra_field_flattened(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        product = await Product.query.filter(name="Alpha").get()
        dump = await filter_selected_fields(product, "id,name,extra_priority")

        assert dump["extra_priority"] == 2
        assert "extra" not in dump


async def test_create_stores_the_extra_field_value(setup_db: FastEdgy) -> None:
    with use_request() as request:
        _declare_extra_fields()

        item = await create_item_action(
            request,
            Product,
            generate_input_create_model(Product)(name="Delta", price=Decimal("4.00"), extra_priority=7),
            fields="id,name,extra_priority",
        )

        assert item["extra_priority"] == 7
        assert (await Product.query.filter(name="Delta").get()).extra == {"priority": 7}


async def test_patch_keeps_the_extra_fields_left_out_of_the_payload(setup_db: FastEdgy) -> None:
    with use_request() as request:
        _declare_extra_fields()
        await _create_products()

        product = await Product.query.filter(name="Alpha").get()
        await patch_item_action(
            request,
            Product,
            product.id,
            generate_input_patch_model(Product)(extra_priority=9),
        )

        assert (await Product.query.filter(name="Alpha").get()).extra == {"priority": 9, "owner": "ada"}


async def test_create_refuses_an_undeclared_extra_field(setup_db: FastEdgy) -> None:
    with use_request() as request:
        _declare_extra_fields()

        with pytest.raises(HTTPException) as raised:
            await create_item_action(
                request,
                Product,
                generate_input_create_model(Product)(name="Epsilon", price=Decimal("5.00"), extra_unknown=1),
            )

        assert raised.value.status_code == 422


async def test_selection_returns_null_for_a_record_without_extra(setup_db: FastEdgy) -> None:
    with use_request():
        _declare_extra_fields()
        await _create_products()

        product = await Product.query.filter(name="Gamma").get()
        dump = await filter_selected_fields(product, "id,extra_priority")

        assert dump["extra_priority"] is None


async def _store_extra_field(workspace, name: str, field_type: WorkspaceExtraFieldType) -> None:
    field = _extra_field(name, field_type)
    field.workspace = workspace

    await field.save()


def _workspace_request(slug: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/{slug}/products",
            "query_string": b"",
            "headers": [],
            "path_params": {"workspace": slug},
        }
    )


async def test_entering_a_workspace_loads_the_fields_it_declared(setup_db: FastEdgy) -> None:
    """No dependency of its own to wire: the workspace is what carries them."""
    user = await create_user(email="ada@example.io")
    acme = await create_workspace(slug="acme", name="Acme")
    other = await create_workspace(slug="other", name="Other")
    await WorkspaceUser(user=user, workspace=acme).save()
    await _store_extra_field(acme, "priority", WorkspaceExtraFieldType.integer)
    await _store_extra_field(other, "budget", WorkspaceExtraFieldType.float)

    token = context.set_request(_workspace_request("acme"))

    try:
        await get_current_workspace(current_user=user)

        assert sorted(context.get_map_workspace_extra_fields("product")) == ["priority"]
    finally:
        context.reset_request(token)


async def test_metadata_carries_the_extra_fields_of_the_current_workspace(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    with use_request():
        _declare_extra_fields()
        metadata = await registry.get_metadata("product")

        assert metadata.fields["extra_priority"].extra is True
        assert metadata.fields["extra_priority"].type == "integer"
        assert "extra" not in metadata.fields
        assert "extra_priority" in (await registry.get_map_models())["product"].fields


async def test_metadata_types_a_rich_text_extra_field_and_filters_it_as_text(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    with use_request():
        context.set_workspace_extra_fields(
            [
                _extra_field("summary", WorkspaceExtraFieldType.rich_text),
                _extra_field("notes", WorkspaceExtraFieldType.text),
            ]
        )
        fields = (await registry.get_metadata("product")).fields

        assert fields["extra_summary"].type == "rich_text"
        assert fields["extra_summary"].filter_operators == fields["extra_notes"].filter_operators != []


async def test_metadata_never_keeps_the_extra_fields_of_another_workspace(setup_db: FastEdgy) -> None:
    """The generated metadata is cached for the whole process: a workspace that
    left its fields in it would hand them to every other one, and to itself
    unchanged until the next restart."""
    registry = get_service(MetadataModelRegistry)

    with use_request():
        _declare_extra_fields()

        assert "extra_priority" in (await registry.get_metadata("product")).fields

    with use_request():
        assert "extra_priority" not in (await registry.get_metadata("product")).fields
        assert "extra_priority" not in (await registry.get_map_models())["product"].fields


async def test_a_model_resolves_from_metadata_carrying_extra_fields(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    with use_request():
        _declare_extra_fields()
        metadata = await registry.get_metadata("product")

        assert await registry.get_model_from_metadata(metadata) is Product


async def test_metadata_carries_the_choices_a_field_declares(setup_db: FastEdgy, monkeypatch) -> None:
    """An application that adds a type backed by a closed list of values says so
    by overriding `metadata_choices`: without it the field reads as free text,
    and an agent only learns its value was refused by writing it."""
    monkeypatch.setattr(
        WorkspaceExtraField,
        "metadata_choices",
        lambda self: {"high": "high", "low": "low"} if self.name == "priority" else None,
    )

    with use_request():
        _declare_extra_fields()
        metadata = await get_service(MetadataModelRegistry).get_metadata("product")

        assert metadata.fields["extra_priority"].choices == {"high": "high", "low": "low"}
        assert metadata.fields["extra_owner"].choices is None


async def _stored_field(workspace, name: str, field_type: WorkspaceExtraFieldType, **extra) -> WorkspaceExtraField:
    field = WorkspaceExtraField(
        label=name.title(),
        name=name,
        field_type=field_type,
        model=WorkspaceExtraFieldModel.product,
        required=False,
        **extra,
    )
    field.workspace = workspace

    await field.save()

    return field


async def test_the_models_a_field_may_target_come_from_the_mixin(setup_db: FastEdgy) -> None:
    """No list is written anywhere: a model joins the choices by carrying
    `ExtendableMixin`, and one that does not cannot be named at all."""
    names = set(WorkspaceExtraFieldModel.__members__)

    assert "product" in names
    assert "category" not in names


async def test_a_value_outside_the_declared_list_is_refused(setup_db: FastEdgy) -> None:
    with use_request() as request:
        context.set_workspace_extra_fields(
            [
                WorkspaceExtraField(
                    label="Stage",
                    name="stage",
                    field_type=WorkspaceExtraFieldType.choice,
                    model=WorkspaceExtraFieldModel.product,
                    options=[{"value": "Seed", "color": 3}, {"value": "Series A", "color": 6}],
                )
            ]
        )

        with pytest.raises(HTTPException) as raised:
            await create_item_action(
                request,
                Product,
                generate_input_create_model(Product)(name="Zeta", price=Decimal("1.00"), extra_stage="Series B"),
            )

        assert raised.value.status_code == 422
        assert "Seed, Series A" in str(raised.value.detail)


async def test_a_boolean_is_not_an_integer(setup_db: FastEdgy) -> None:
    """`bool` is an `int` in Python, and pydantic follows: without a guard,
    `true` would pass for an integer and be stored as one."""
    with use_request() as request:
        _declare_extra_fields()

        with pytest.raises(HTTPException) as raised:
            await create_item_action(
                request,
                Product,
                generate_input_create_model(Product)(name="Eta", price=Decimal("1.00"), extra_priority=True),
            )

        assert raised.value.status_code == 422


async def test_a_half_coloured_list_of_values_is_refused(setup_db: FastEdgy) -> None:
    """A client renders a chip for what carries a colour and bare text for what
    does not: a mixed list displays broken with nothing having said so."""
    workspace = await create_workspace(slug="acme", name="Acme")

    with pytest.raises(HTTPException) as raised:
        await _stored_field(
            workspace,
            "stage",
            WorkspaceExtraFieldType.choice,
            options=[{"value": "Seed", "color": 3}, "Series A"],
        )

    assert raised.value.status_code == 422


async def test_a_list_of_values_refuses_a_duplicate(setup_db: FastEdgy) -> None:
    workspace = await create_workspace(slug="acme", name="Acme")

    with pytest.raises(HTTPException) as raised:
        await _stored_field(workspace, "stage", WorkspaceExtraFieldType.choice, options=["Seed", "Seed"])

    assert raised.value.status_code == 422


async def test_dropping_an_option_takes_it_off_the_records(setup_db: FastEdgy) -> None:
    """The list of options is the only authority on what exists: a value it no
    longer carries would show without its chip and filter on nothing."""
    workspace = await create_workspace(slug="acme", name="Acme")
    field = await _stored_field(workspace, "stage", WorkspaceExtraFieldType.choice, options=["Seed", "Series A"])
    await Product.query.create(name="Alpha", price=Decimal("1.00"), extra={"stage": "Seed"})

    field.workspace = workspace
    field.options = ["Series A"]
    await field.save()

    assert (await Product.query.filter(name="Alpha").get()).extra == {"stage": None}


async def test_deleting_a_field_takes_its_values_off_the_records(setup_db: FastEdgy) -> None:
    workspace = await create_workspace(slug="acme", name="Acme")
    field = await _stored_field(workspace, "priority", WorkspaceExtraFieldType.integer)
    await Product.query.create(name="Alpha", price=Decimal("1.00"), extra={"priority": 2, "owner": "ada"})

    await field.delete()

    assert (await Product.query.filter(name="Alpha").get()).extra == {"owner": "ada"}


async def test_metadata_says_which_models_accept_a_custom_field(setup_db: FastEdgy) -> None:
    registry = get_service(MetadataModelRegistry)

    assert (await registry.get_metadata("product")).has_extra_fields is True
    assert (await registry.get_metadata("category")).has_extra_fields is False


async def test_a_colour_outside_the_palette_is_refused(setup_db: FastEdgy, override_settings) -> None:
    """The application defines its palette, the framework only holds an option
    to the index it declares: an index it could not render is refused."""
    override_settings(workspace_extra_field_option_colors=["#0E8F7E", "#0C8FA7"])
    workspace = await create_workspace(slug="acme", name="Acme")

    with pytest.raises(HTTPException) as raised:
        await _stored_field(
            workspace,
            "stage",
            WorkspaceExtraFieldType.choice,
            options=[{"value": "Seed", "color": 2}],
        )

    assert raised.value.status_code == 422

    await _stored_field(
        workspace,
        "stage",
        WorkspaceExtraFieldType.choice,
        options=[{"value": "Seed", "color": 1}],
    )


async def test_a_model_joins_the_choices_by_name_not_by_import_order(setup_db: FastEdgy) -> None:
    """A Postgres enum keeps the order it was declared in, and the order the
    models arrive in is the order they are imported: placing a member by name
    is what stops a change of import order from becoming a migration."""
    from fastedgy.orm.fields.field_choice import ExtendableChoiceEnum

    class Models(ExtendableChoiceEnum):
        pass

    for name in ("zebra", "alpha", "middle"):
        Models.extend(name, name.title(), before=next((one for one in Models.__members__ if one > name), None))

    assert list(Models.__members__) == ["alpha", "middle", "zebra"]
    assert [one.name for one in Models] == ["alpha", "middle", "zebra"]


async def test_an_application_without_extendable_models_pays_nothing(setup_db: FastEdgy, monkeypatch) -> None:
    """What every application that does not use custom fields runs on each
    request: one test on an empty mapping. The registry is walked once, to say
    so if a custom field model is declared against nothing, and never again."""
    from fastedgy.orm import extra_fields as helpers

    walks = 0

    def counted() -> None:
        nonlocal walks
        walks += 1

    monkeypatch.setattr(WorkspaceExtraFieldModel, "_member_map_", {})
    monkeypatch.setattr(helpers, "find_workspace_extra_field_model", counted)
    helpers._warn_when_nothing_is_extendable.cache_clear()

    with use_request():
        context.set_workspace(await create_workspace(slug="acme", name="Acme"))

        await load_workspace_extra_fields()
        await load_workspace_extra_fields()

        assert walks == 1
        assert context.get_workspace_extra_fields() == []

    metadata = await get_service(MetadataModelRegistry).get_metadata("product")

    assert "extra_priority" not in metadata.fields

    helpers._warn_when_nothing_is_extendable.cache_clear()


async def test_the_extra_field_model_is_resolved_once(setup_db: FastEdgy) -> None:
    """Walking every registered model to find it, on every request, is what the
    cache is there to stop."""
    from fastedgy.orm.extra_fields import find_workspace_extra_field_model

    find_workspace_extra_field_model.cache_clear()
    first = find_workspace_extra_field_model()
    second = find_workspace_extra_field_model()

    assert first is second
    assert find_workspace_extra_field_model.cache_info().misses == 1
    assert find_workspace_extra_field_model.cache_info().hits == 1


async def test_nothing_is_loaded_outside_a_workspace(setup_db: FastEdgy) -> None:
    """A route with no workspace in its path never enters one, and an
    application without workspaces never has one at all."""
    with use_request():
        await load_workspace_extra_fields()

        assert context.get_workspace_extra_fields() == []


async def test_an_application_may_offer_fewer_types(setup_db: FastEdgy) -> None:
    """Restricting narrows the column type itself, so what the API accepts and
    what the metadata offers stay the same list, with nothing to keep in sync.
    The member stays on the class, so code that mentions it still reads."""
    from fastedgy.orm import fields
    from fastedgy.orm.fields.field_choice import ExtendableChoiceEnum

    class Types(ExtendableChoiceEnum):
        boolean = "Boolean"
        char = "Char"
        choice = "List of values"
        date = "Date"

    field = cast(Any, fields.ChoiceField(Types, null=True))
    Types.restrict("boolean", "char")

    assert field.column_type.enums == ["boolean", "char"]
    assert set(field._choice_labels) == {"boolean", "char"}
    assert [one.name for one in field.choices] == ["boolean", "char"]

    # Hidden, not removed: the framework mentions `choice` by attribute and
    # must not break because an application stopped offering it.
    assert Types.choice.name == "choice"
    assert list(Types.__members__) == ["boolean", "char", "choice", "date"]

    with pytest.raises(ValueError):
        Types.restrict("nope")


async def test_a_custom_field_model_opening_onto_nothing_says_so(setup_db: FastEdgy, monkeypatch, caplog) -> None:
    """The one case where the feature does nothing and would otherwise say
    nothing: a model declared for custom fields, and no model holding the
    column to receive them."""
    from fastedgy.orm import extra_fields as helpers

    monkeypatch.setattr(WorkspaceExtraFieldModel, "_member_map_", {})
    helpers._warn_when_nothing_is_extendable.cache_clear()

    with caplog.at_level("WARNING", logger="fastedgy.extra_fields"), use_request():
        context.set_workspace(await create_workspace(slug="acme", name="Acme"))

        await load_workspace_extra_fields()

    assert "no model holds the `extra` column" in caplog.text

    helpers._warn_when_nothing_is_extendable.cache_clear()


async def test_a_workspace_reads_its_fields_once_per_window(setup_db: FastEdgy, override_settings) -> None:
    """Entering a workspace happens on every request and the fields change a few
    times a year: the row is deleted behind the cache to prove nothing was read
    again, then the cache is dropped the way a write drops it."""
    from fastedgy.orm.extra_fields import invalidate_workspace_extra_fields

    override_settings(workspace_extra_field_cache_seconds=60.0)
    workspace = await create_workspace(slug="acme", name="Acme")
    field = await _stored_field(workspace, "priority", WorkspaceExtraFieldType.integer)
    invalidate_workspace_extra_fields()

    with use_request():
        context.set_workspace(workspace)
        await load_workspace_extra_fields()

        assert [one.name for one in context.get_workspace_extra_fields()] == ["priority"]

    await type(field).query.filter(id=field.id).delete()

    with use_request():
        context.set_workspace(workspace)
        await load_workspace_extra_fields()

        assert [one.name for one in context.get_workspace_extra_fields()] == ["priority"]

    invalidate_workspace_extra_fields(workspace.id)

    with use_request():
        context.set_workspace(workspace)
        await load_workspace_extra_fields()

        assert context.get_workspace_extra_fields() == []


async def test_writing_a_field_drops_what_this_worker_had_read(setup_db: FastEdgy, override_settings) -> None:
    from fastedgy.orm.extra_fields import invalidate_workspace_extra_fields

    override_settings(workspace_extra_field_cache_seconds=60.0)
    workspace = await create_workspace(slug="acme", name="Acme")
    invalidate_workspace_extra_fields()

    with use_request():
        context.set_workspace(workspace)
        await load_workspace_extra_fields()

        assert context.get_workspace_extra_fields() == []

    await _stored_field(workspace, "priority", WorkspaceExtraFieldType.integer)

    with use_request():
        context.set_workspace(workspace)
        await load_workspace_extra_fields()

        assert [one.name for one in context.get_workspace_extra_fields()] == ["priority"]


async def test_a_write_from_another_process_drops_what_this_one_cached(setup_db: FastEdgy, override_settings) -> None:
    """Why the channel exists: production runs several containers of several
    workers, so the write lands in a process that is not the one holding the
    stale copy. Here the notification goes out through Postgres and comes back
    on this process's own listener, which is exactly the path it takes between
    two containers."""
    import asyncio

    from fastedgy.orm.extra_fields import (
        announce_workspace_extra_fields,
        workspace_extra_fields_are_watched,
    )

    assert workspace_extra_fields_are_watched(), "the listener is what makes the cache trustworthy"

    override_settings(workspace_extra_field_cache_seconds=60.0)
    workspace = await create_workspace(slug="acme", name="Acme")
    field = await _stored_field(workspace, "priority", WorkspaceExtraFieldType.integer)

    with use_request():
        context.set_workspace(workspace)
        await load_workspace_extra_fields()

        assert [one.name for one in context.get_workspace_extra_fields()] == ["priority"]

    # The other process writes and says so. Nothing is dropped here by hand.
    await type(field).query.filter(id=field.id).delete()
    await announce_workspace_extra_fields(workspace.id)

    for _ in range(100):
        with use_request():
            context.set_workspace(workspace)
            await load_workspace_extra_fields()

            if context.get_workspace_extra_fields() == []:
                return

        await asyncio.sleep(0.02)

    raise AssertionError("the notification never reached this process")


async def test_the_listener_stops_without_hanging_the_shutdown() -> None:
    """Shutting down must not wait on a socket that stopped answering, which is
    the very case this listener exists to survive."""
    from fastedgy.orm.extra_field_invalidator import ExtraFieldInvalidator

    invalidator = ExtraFieldInvalidator("fastedgy_extra_fields_unused")

    await invalidator.stop()

    await invalidator.start()
    await invalidator.stop()

    assert invalidator.listening is False

    await invalidator.stop()
