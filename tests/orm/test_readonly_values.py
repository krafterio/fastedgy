# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""``apply_readonly_values``: the explicit code-side escape hatch to persist
``read_only`` fields, which Edgy silently drops on every regular write path."""

from datetime import UTC, datetime
from typing import Any

import pytest

from fastedgy.app import FastEdgy
from fastedgy.orm.filter import R
from fastedgy.orm.signals import post_save
from fastedgy.test.factories import create_user, create_workspace, create_workspace_user
from fastedgy.test.models.product import Product
from fastedgy.test.models.workspace import Workspace
from fastedgy.test.models.workspace_user import WorkspaceUser

TARGET = datetime(2000, 1, 1, 12, 0, 0)


async def test_regular_writes_still_drop_read_only_fields(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Probe", price="1.00", created_at=TARGET)

    fetched = await Product.query.get(id=product.id)
    assert fetched.created_at != TARGET

    fetched.created_at = TARGET
    await fetched.save()

    assert (await Product.query.get(id=product.id)).created_at != TARGET


async def test_apply_readonly_values_persists_on_insert(setup_db: FastEdgy) -> None:
    product = Product(name="Probe", price="1.00")
    product.apply_readonly_values({"created_at": TARGET})
    await product.save()

    fetched = await Product.query.get(id=product.id)
    assert fetched.created_at.replace(tzinfo=None) == TARGET


async def test_apply_readonly_values_persists_on_update(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Probe", price="1.00")

    fetched = await Product.query.get(id=product.id)
    fetched.apply_readonly_values({"created_at": TARGET})
    await fetched.save()

    reloaded = await Product.query.get(id=product.id)
    assert reloaded.created_at.replace(tzinfo=None) == TARGET
    assert reloaded.name == "Probe"


async def test_overrides_are_consumed_by_the_save(setup_db: FastEdgy) -> None:
    product = await Product.query.create(name="Probe", price="1.00")

    fetched = await Product.query.get(id=product.id)
    fetched.apply_readonly_values({"created_at": TARGET})
    await fetched.save()

    assert fetched._readonly_overrides == {}


async def test_unknown_field_is_rejected(setup_db: FastEdgy) -> None:
    product = Product(name="Probe", price="1.00")

    with pytest.raises(ValueError, match="Unknown field 'nope'"):
        product.apply_readonly_values({"nope": 1})


async def _membership() -> tuple[WorkspaceUser, Workspace, Workspace]:
    user = await create_user(email="owner@example.io")
    acme = await create_workspace(slug="acme")
    beta = await create_workspace(slug="beta")

    return await create_workspace_user(user, acme), acme, beta


async def test_a_queryset_update_writes_the_read_only_values_it_was_handed(setup_db: FastEdgy) -> None:
    membership, _, _ = await _membership()
    rows = WorkspaceUser.query.filter(R("id", "=", membership.id))

    await rows.update(is_default=True)

    assert (await WorkspaceUser.query.get(id=membership.id)).is_default is False

    await rows.apply_readonly_values({"is_default": True}).filter(R("id", ">", 0)).update()

    assert (await WorkspaceUser.query.get(id=membership.id)).is_default is True


async def test_a_queryset_refuses_an_unknown_read_only_value(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError, match="Unknown field 'nope'"):
        WorkspaceUser.query.apply_readonly_values({"nope": 1})


async def test_a_save_keeps_the_read_only_relations_in_memory_and_in_post_save(setup_db: FastEdgy) -> None:
    membership, acme, _ = await _membership()
    fetched = await WorkspaceUser.query.get(id=membership.id)
    seen: list[tuple[int | None, int | None]] = []

    async def saved(sender: Any, instance: WorkspaceUser, **_: Any) -> None:
        seen.append((getattr(instance.workspace, "id", None), getattr(instance.user, "id", None)))

    with post_save.connected_to(saved, sender=WorkspaceUser):
        await fetched.save()

    assert membership.user is not None
    expected = (acme.id, membership.user.id)
    assert seen == [expected]
    assert (getattr(fetched.workspace, "id", None), getattr(fetched.user, "id", None)) == expected


async def test_a_read_only_relation_assigned_then_saved_is_written(setup_db: FastEdgy) -> None:
    membership, _, beta = await _membership()
    fetched = await WorkspaceUser.query.get(id=membership.id)

    fetched.workspace = beta
    await fetched.save()

    assert (await WorkspaceUser.query.get(id=membership.id)).workspace.id == beta.id


async def test_a_stale_copy_writes_its_read_only_relations_back_unless_saved_with_values(setup_db: FastEdgy) -> None:
    membership, acme, beta = await _membership()
    partial, full, moved = [await WorkspaceUser.query.get(id=membership.id) for _ in range(3)]

    moved.apply_readonly_values({"workspace": beta})
    await moved.save()
    await partial.save(values={"updated_at": datetime.now(UTC)})

    assert (await WorkspaceUser.query.get(id=membership.id)).workspace.id == beta.id

    await full.save()

    assert (await WorkspaceUser.query.get(id=membership.id)).workspace.id == acme.id


async def test_a_queryset_holds_its_staged_values_out_of_reach_of_the_others(setup_db: FastEdgy) -> None:
    rows = WorkspaceUser.query.filter(R("id", ">", 0))
    staged = rows.apply_readonly_values({"is_default": True})

    for queryset in (rows, staged):
        with pytest.raises(TypeError):
            queryset._readonly_overrides["is_default"] = False

    assert dict(staged._readonly_overrides) == {"is_default": True}
    assert dict(WorkspaceUser.query.filter(R("id", ">", 0))._readonly_overrides) == {}
