from __future__ import annotations

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.enums import (
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import User
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


async def test_cp02_owner_cannot_be_inserted_non_approved(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    invalid_owner = User(
        role=UserRole.OWNER,
        access_status=UserAccessStatus.BLOCKED,
    )
    db.add(invalid_owner)

    with pytest.raises(DBAPIError):
        await db.flush()


async def test_cp02_existing_owner_cannot_become_non_approved(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    owner, _ = await actor(
        db,
        UserRole.OWNER,
        UserAccessStatus.APPROVED,
    )

    with pytest.raises(DBAPIError):
        await db.execute(
            update(User)
            .where(User.id == owner.id)
            .values(
                access_status=UserAccessStatus.BLOCKED,
            )
        )


async def test_cp02_direct_access_status_change_without_audit_is_rejected(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    target, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    with pytest.raises(DBAPIError):
        await db.execute(
            update(User)
            .where(User.id == target.id)
            .values(
                access_status=UserAccessStatus.BLOCKED,
            )
        )

        # Audit coupling is intentionally DEFERRABLE so the legitimate
        # user mutation and immutable audit event may be flushed in either
        # order inside one transaction. Force the transaction-end check here.
        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_cp02_direct_role_change_without_audit_is_rejected(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    target, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    with pytest.raises(DBAPIError):
        await db.execute(
            update(User)
            .where(User.id == target.id)
            .values(
                role=UserRole.SENIOR_ENGINEER,
            )
        )

        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_cp02_legitimate_access_service_satisfies_db_audit_coupling(
    warehouse_db: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.modules.identity.admin_service import (
        update_user_access,
    )
    from app.modules.identity.models import (
        UserAccessEvent,
    )

    db = warehouse_db

    admin, _ = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    target, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    await update_user_access(
        db,
        actor_user_id=admin.id,
        target_user_id=target.id,
        access_status=UserAccessStatus.BLOCKED,
        recovery_telegram_user_id=None,
    )

    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    event = await db.scalar(
        select(UserAccessEvent)
        .where(
            UserAccessEvent.target_user_id == target.id,
            UserAccessEvent.before_access_status == UserAccessStatus.APPROVED,
            UserAccessEvent.after_access_status == UserAccessStatus.BLOCKED,
        )
        .order_by(UserAccessEvent.occurred_at.desc())
        .limit(1)
    )

    assert event is not None
    assert event.db_transaction_id > 0


async def test_cp02_legitimate_role_service_satisfies_db_audit_coupling(
    warehouse_db: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.modules.identity.admin_service import (
        update_user_role,
    )
    from app.modules.identity.models import (
        UserRoleEvent,
    )

    db = warehouse_db

    owner, _ = await actor(
        db,
        UserRole.OWNER,
        UserAccessStatus.APPROVED,
    )
    target, _ = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    await update_user_role(
        db,
        actor_user_id=owner.id,
        target_user_id=target.id,
        role=UserRole.SENIOR_ENGINEER,
        recovery_telegram_user_id=None,
    )

    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    event = await db.scalar(
        select(UserRoleEvent)
        .where(
            UserRoleEvent.target_user_id == target.id,
            UserRoleEvent.before_role == UserRole.ENGINEER,
            UserRoleEvent.after_role == UserRole.SENIOR_ENGINEER,
        )
        .order_by(UserRoleEvent.occurred_at.desc())
        .limit(1)
    )

    assert event is not None
    assert event.db_transaction_id > 0
