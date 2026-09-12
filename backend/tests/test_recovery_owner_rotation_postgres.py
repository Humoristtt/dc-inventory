import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.recovery_owner_rotation import (
    RecoveryOwnerRotationError,
    rotate_recovery_owner_transaction,
)
from app.modules.auth.models import AuthSession
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    User,
    UserAccessEvent,
    UserRoleEvent,
)
from app.modules.inventory.models import UserItemCustodyBalance
from tests.warehouse_helpers import scenario

NOW = datetime(2026, 9, 12, 6, 30, tzinfo=UTC)


async def create_user(
    db: AsyncSession,
    *,
    telegram_user_id: int,
    role: UserRole,
    access_status: UserAccessStatus,
) -> User:
    user = User(
        id=uuid.uuid4(),
        role=role,
        access_status=access_status,
        approved_at=(
            NOW
            if access_status == UserAccessStatus.APPROVED
            else None
        ),
    )
    db.add(
        TelegramIdentity(
            user=user,
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            first_name="Rotation test",
        )
    )
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_rotation_is_atomic_audited_and_resolves_pending_access(
    warehouse_db: AsyncSession,
) -> None:
    old_owner = await create_user(
        warehouse_db,
        telegram_user_id=930001,
        role=UserRole.OWNER,
        access_status=UserAccessStatus.APPROVED,
    )
    target = await create_user(
        warehouse_db,
        telegram_user_id=930002,
        role=UserRole.ENGINEER,
        access_status=UserAccessStatus.PENDING,
    )

    pending = AccessRequest(
        user_id=target.id,
        status=AccessRequestStatus.PENDING,
    )
    old_session = AuthSession(
        user_id=old_owner.id,
        token_hash=b"a" * 32,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    target_session = AuthSession(
        user_id=target.id,
        token_hash=b"b" * 32,
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    warehouse_db.add_all(
        [
            pending,
            old_session,
            target_session,
        ]
    )
    await warehouse_db.flush()

    result = await rotate_recovery_owner_transaction(
        warehouse_db,
        configured_recovery_telegram_user_id=930001,
        target_telegram_user_id=930002,
        confirmed_target_user_id=target.id,
        now=NOW,
    )

    await warehouse_db.refresh(old_owner)
    await warehouse_db.refresh(target)
    await warehouse_db.refresh(pending)
    await warehouse_db.refresh(old_session)
    await warehouse_db.refresh(target_session)

    assert old_owner.role == UserRole.ADMIN
    assert target.role == UserRole.OWNER
    assert target.access_status == UserAccessStatus.APPROVED
    assert target.approved_by_user_id == old_owner.id

    assert pending.status == AccessRequestStatus.APPROVED
    assert pending.decided_by_user_id == old_owner.id
    assert pending.decision_note == "recovery OWNER rotation"

    assert old_session.revoked_at == NOW
    assert target_session.revoked_at == NOW

    assert (
        await warehouse_db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.OWNER)
        )
        == 1
    )

    role_events = list(
        (
            await warehouse_db.scalars(
                select(UserRoleEvent).where(
                    UserRoleEvent.actor_user_id
                    == old_owner.id,
                    UserRoleEvent.target_user_id.in_(
                        [old_owner.id, target.id]
                    ),
                )
            )
        ).all()
    )
    assert len(role_events) == 2

    access_event = await warehouse_db.scalar(
        select(UserAccessEvent).where(
            UserAccessEvent.actor_user_id
            == old_owner.id,
            UserAccessEvent.target_user_id
            == target.id,
            UserAccessEvent.before_access_status
            == UserAccessStatus.PENDING,
            UserAccessEvent.after_access_status
            == UserAccessStatus.APPROVED,
        )
    )
    assert access_event is not None

    assert result["owner_count"] == 1
    assert result["new_owner_user_id"] == str(target.id)
    assert result["pending_access_request_resolved"] is True


@pytest.mark.asyncio
async def test_rotation_rejects_wrong_confirmed_target_uuid(
    warehouse_db: AsyncSession,
) -> None:
    old_owner = await create_user(
        warehouse_db,
        telegram_user_id=930011,
        role=UserRole.OWNER,
        access_status=UserAccessStatus.APPROVED,
    )
    target = await create_user(
        warehouse_db,
        telegram_user_id=930012,
        role=UserRole.ADMIN,
        access_status=UserAccessStatus.APPROVED,
    )

    with pytest.raises(
        RecoveryOwnerRotationError,
        match="confirmed target user UUID",
    ):
        await rotate_recovery_owner_transaction(
            warehouse_db,
            configured_recovery_telegram_user_id=930011,
            target_telegram_user_id=930012,
            confirmed_target_user_id=uuid.uuid4(),
            now=NOW,
        )

    await warehouse_db.refresh(old_owner)
    await warehouse_db.refresh(target)

    assert old_owner.role == UserRole.OWNER
    assert target.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_rotation_rejects_target_with_outstanding_custody(
    warehouse_db: AsyncSession,
) -> None:
    target_id, item_id, _source, _destination = await scenario(
        warehouse_db,
        UserRole.ENGINEER,
    )
    target_identity = await warehouse_db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.user_id == target_id
        )
    )
    assert target_identity is not None

    old_owner = await create_user(
        warehouse_db,
        telegram_user_id=930021,
        role=UserRole.OWNER,
        access_status=UserAccessStatus.APPROVED,
    )

    warehouse_db.add(
        UserItemCustodyBalance(
            user_id=target_id,
            item_id=item_id,
            quantity=1,
        )
    )
    await warehouse_db.flush()

    with pytest.raises(
        RecoveryOwnerRotationError,
        match="outstanding equipment custody",
    ):
        await rotate_recovery_owner_transaction(
            warehouse_db,
            configured_recovery_telegram_user_id=930021,
            target_telegram_user_id=(
                target_identity.telegram_user_id
            ),
            confirmed_target_user_id=target_id,
            now=NOW,
        )

    await warehouse_db.refresh(old_owner)

    assert old_owner.role == UserRole.OWNER
    assert (
        await warehouse_db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.OWNER)
        )
        == 1
    )
