from __future__ import annotations

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from app.db.health import (
    DatabaseUnavailableError,
    ensure_database_ready,
)
from app.modules.catalog.models import (
    CategoryAttribute,
    Item,
    ItemAttributeValue,
)
from app.modules.catalog.service import create_item
from app.modules.identity.enums import (
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import User, UserRoleEvent
from app.modules.inventory.models import UserItemCustodyBalance
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


async def test_cp02_required_catalog_attribute_cannot_be_deleted(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    item = await db.get(Item, item_id)
    assert item is not None

    required_attribute = await db.scalar(
        select(CategoryAttribute)
        .where(
            CategoryAttribute.category_id == item.category_id,
            CategoryAttribute.required.is_(True),
        )
        .order_by(
            CategoryAttribute.sort_order,
            CategoryAttribute.key,
        )
        .limit(1)
    )

    assert required_attribute is not None

    stored_value = await db.scalar(
        select(ItemAttributeValue).where(
            ItemAttributeValue.item_id == item_id,
            ItemAttributeValue.category_attribute_id == required_attribute.id,
        )
    )

    assert stored_value is not None

    with pytest.raises(DBAPIError):
        await db.execute(delete(ItemAttributeValue).where(ItemAttributeValue.id == stored_value.id))

        # The intended invariant may be deferred because catalog update
        # legitimately replaces EAV rows inside one transaction.
        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_cp02_ineligible_role_cannot_receive_custody_projection(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    manager, _ = await actor(
        db,
        UserRole.MANAGER,
        UserAccessStatus.APPROVED,
    )

    item_id = await create_item(
        db,
        cable_payload(),
    )

    db.add(
        UserItemCustodyBalance(
            user_id=manager.id,
            item_id=item_id,
            quantity=1,
        )
    )

    with pytest.raises(DBAPIError):
        await db.flush()


async def test_cp02_existing_custody_blocks_audited_role_demotion_at_db_boundary(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    owner, _ = await actor(
        db,
        UserRole.OWNER,
        UserAccessStatus.APPROVED,
    )

    holder, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    item_id = await create_item(
        db,
        cable_payload(),
    )

    db.add(
        UserItemCustodyBalance(
            user_id=holder.id,
            item_id=item_id,
            quantity=1,
        )
    )
    await db.flush()

    # Supply a valid same-transaction role audit row, so the CP-02.2
    # audit-coupling invariant is satisfied. The remaining failure must
    # therefore come specifically from custody eligibility.
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


async def test_cp02_readiness_rejects_missing_critical_db_trigger(
    migration_database: str,
) -> None:
    from tests.migration_helpers import alembic

    alembic(
        migration_database,
        "upgrade",
        "head",
    )

    engine = create_async_engine(
        migration_database,
        pool_pre_ping=True,
    )

    try:
        await ensure_database_ready(engine)

        async with engine.begin() as connection:
            await connection.execute(text("DROP TRIGGER trg_users_require_access_audit ON users"))

        with pytest.raises(DatabaseUnavailableError):
            await ensure_database_ready(engine)

    finally:
        await engine.dispose()


async def test_cp02_catalog_update_can_replace_required_eav_rows(
    warehouse_db: AsyncSession,
) -> None:
    from app.modules.catalog.schemas import ItemPatch
    from app.modules.catalog.service import update_item

    db = warehouse_db

    payload = cable_payload()
    item_id = await create_item(db, payload)

    await update_item(
        db,
        item_id,
        ItemPatch(
            attributes=dict(payload.attributes),
        ),
        fields_set={"attributes"},
    )

    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_cp02_eligible_user_can_receive_custody_projection(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    holder, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    item_id = await create_item(
        db,
        cable_payload(),
    )

    db.add(
        UserItemCustodyBalance(
            user_id=holder.id,
            item_id=item_id,
            quantity=1,
        )
    )

    await db.flush()

    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
