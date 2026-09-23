"""Изолированные PostgreSQL-регрессии инвариантов каталога и выдачи (f7)."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import CategoryAttribute, Item, ItemAttributeValue
from app.modules.catalog.schemas import ItemPatch
from app.modules.catalog.service import create_item, update_item
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User, UserRoleEvent
from app.modules.inventory.models import UserItemCustodyBalance
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


async def test_f7_cannot_remove_last_required_item_attribute(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(db, cable_payload())
    item = await db.get(Item, item_id)
    assert item is not None
    required = await db.scalar(
        select(CategoryAttribute)
        .where(
            CategoryAttribute.category_id == item.category_id,
            CategoryAttribute.required.is_(True),
        )
        .limit(1)
    )
    assert required is not None
    value = await db.scalar(
        select(ItemAttributeValue).where(
            ItemAttributeValue.item_id == item_id,
            ItemAttributeValue.category_attribute_id == required.id,
        )
    )
    assert value is not None

    with pytest.raises(DBAPIError):
        await db.execute(delete(ItemAttributeValue).where(ItemAttributeValue.id == value.id))
        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_f7_manager_cannot_receive_custody_projection(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    manager, _ = await actor(db, UserRole.MANAGER, UserAccessStatus.APPROVED)
    item_id = await create_item(db, cable_payload())
    db.add(UserItemCustodyBalance(user_id=manager.id, item_id=item_id, quantity=1))

    with pytest.raises(DBAPIError):
        await db.flush()


async def test_f7_custody_blocks_audited_demotion_at_commit_boundary(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    owner, _ = await actor(db, UserRole.OWNER, UserAccessStatus.APPROVED)
    holder, _ = await actor(db, UserRole.ENGINEER, UserAccessStatus.APPROVED)
    item_id = await create_item(db, cable_payload())
    db.add(UserItemCustodyBalance(user_id=holder.id, item_id=item_id, quantity=1))
    await db.flush()

    await db.execute(update(User).where(User.id == holder.id).values(role=UserRole.MANAGER))
    db.add(
        UserRoleEvent(
            actor_user_id=owner.id,
            target_user_id=holder.id,
            before_role=UserRole.ENGINEER,
            after_role=UserRole.MANAGER,
        )
    )
    await db.flush()

    with pytest.raises(DBAPIError):
        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_f7_legitimate_catalog_replaces_required_attribute_values(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    payload = cable_payload()
    item_id = await create_item(db, payload)
    await update_item(
        db,
        item_id,
        ItemPatch(attributes=dict(payload.attributes)),
        fields_set={"attributes"},
    )
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_f7_approved_engineer_can_receive_custody(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    engineer, _ = await actor(db, UserRole.ENGINEER, UserAccessStatus.APPROVED)
    item_id = await create_item(db, cable_payload())
    db.add(UserItemCustodyBalance(user_id=engineer.id, item_id=item_id, quantity=1))
    await db.flush()
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
