from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuthSession
from app.modules.identity.admin_service import (
    InvalidAccessTransitionError,
    LastApprovedAdminInvariantError,
    RecoveryAdminInvariantError,
    update_user_access,
)
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import (
    TelegramIdentity,
    User,
    UserAccessEvent,
)


async def _create_user(
    warehouse_db: AsyncSession,
    *,
    telegram_user_id: int,
    role: UserRole = UserRole.USER,
    access_status: UserAccessStatus = UserAccessStatus.APPROVED,
) -> tuple[User, TelegramIdentity]:
    now = datetime.now(UTC)

    user = User(
        id=uuid.uuid4(),
        role=role,
        access_status=access_status,
        approved_at=(
            now
            if access_status == UserAccessStatus.APPROVED
            else None
        ),
    )
    identity = TelegramIdentity(
        id=uuid.uuid4(),
        user=user,
        telegram_user_id=telegram_user_id,
        first_name=f"user-{telegram_user_id}",
        last_auth_at=now,
    )

    warehouse_db.add(user)
    warehouse_db.add(identity)
    await warehouse_db.flush()

    return user, identity


@pytest.mark.asyncio
async def test_admin_can_block_user_and_revoke_sessions(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900001,
        role=UserRole.ADMIN,
    )
    user, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900002,
    )

    now = datetime.now(UTC)

    active = AuthSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=b"a" * 32,
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    expired = AuthSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=b"b" * 32,
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )

    warehouse_db.add_all([active, expired])
    await warehouse_db.flush()

    changed_user, event = await update_user_access(
        warehouse_db,
        actor_user_id=admin.id,
        target_user_id=user.id,
        access_status=UserAccessStatus.BLOCKED,
        recovery_telegram_user_id=900001,
        now=now,
    )

    assert changed_user.access_status == UserAccessStatus.BLOCKED
    assert changed_user.approved_at is None
    assert changed_user.approved_by_user_id is None

    assert event is not None
    assert event.actor_user_id == admin.id
    assert event.target_user_id == user.id
    assert event.before_access_status == UserAccessStatus.APPROVED
    assert event.after_access_status == UserAccessStatus.BLOCKED

    sessions = (
        await warehouse_db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id)
            .order_by(AuthSession.created_at)
        )
    ).all()

    assert len(sessions) == 2
    assert all(session.revoked_at == now for session in sessions)


@pytest.mark.asyncio
async def test_admin_can_unblock_user(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900011,
        role=UserRole.ADMIN,
    )
    user, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900012,
        access_status=UserAccessStatus.BLOCKED,
    )

    now = datetime.now(UTC)

    changed_user, event = await update_user_access(
        warehouse_db,
        actor_user_id=admin.id,
        target_user_id=user.id,
        access_status=UserAccessStatus.APPROVED,
        recovery_telegram_user_id=900011,
        now=now,
    )

    assert changed_user.access_status == UserAccessStatus.APPROVED
    assert changed_user.approved_at == now
    assert changed_user.approved_by_user_id == admin.id

    assert event is not None
    assert event.before_access_status == UserAccessStatus.BLOCKED
    assert event.after_access_status == UserAccessStatus.APPROVED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "target"),
    [
        (
            UserAccessStatus.PENDING,
            UserAccessStatus.BLOCKED,
        ),
        (
            UserAccessStatus.REJECTED,
            UserAccessStatus.APPROVED,
        ),
    ],
)
async def test_access_workflow_cannot_be_bypassed(
    warehouse_db: AsyncSession,
    source: UserAccessStatus,
    target: UserAccessStatus,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900021,
        role=UserRole.ADMIN,
    )
    user, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900022,
        access_status=source,
    )

    with pytest.raises(InvalidAccessTransitionError):
        await update_user_access(
            warehouse_db,
            actor_user_id=admin.id,
            target_user_id=user.id,
            access_status=target,
            recovery_telegram_user_id=900021,
        )


@pytest.mark.asyncio
async def test_recovery_admin_cannot_be_blocked(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900031,
        role=UserRole.ADMIN,
    )

    with pytest.raises(RecoveryAdminInvariantError):
        await update_user_access(
            warehouse_db,
            actor_user_id=admin.id,
            target_user_id=admin.id,
            access_status=UserAccessStatus.BLOCKED,
            recovery_telegram_user_id=900031,
        )


@pytest.mark.asyncio
async def test_last_approved_admin_cannot_be_blocked(
    warehouse_db: AsyncSession,
) -> None:
    # The disposable integration database may contain synthetic users
    # created outside this fixture. Make the invariant state explicit
    # inside this test transaction.
    await warehouse_db.execute(
        update(User)
        .where(
            User.role == UserRole.ADMIN,
            User.access_status == UserAccessStatus.APPROVED,
        )
        .values(
            access_status=UserAccessStatus.BLOCKED,
            approved_at=None,
            approved_by_user_id=None,
        )
    )

    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900035,
        role=UserRole.ADMIN,
    )

    with pytest.raises(
        LastApprovedAdminInvariantError,
        match="last approved administrator cannot be blocked",
    ):
        await update_user_access(
            warehouse_db,
            actor_user_id=admin.id,
            target_user_id=admin.id,
            access_status=UserAccessStatus.BLOCKED,
            recovery_telegram_user_id=None,
        )


@pytest.mark.asyncio
async def test_one_of_two_approved_admins_can_be_blocked(
    warehouse_db: AsyncSession,
) -> None:
    actor, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900036,
        role=UserRole.ADMIN,
    )
    target, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900037,
        role=UserRole.ADMIN,
    )

    changed_user, event = await update_user_access(
        warehouse_db,
        actor_user_id=actor.id,
        target_user_id=target.id,
        access_status=UserAccessStatus.BLOCKED,
        recovery_telegram_user_id=None,
    )

    assert changed_user.access_status == UserAccessStatus.BLOCKED
    assert event is not None
    assert event.before_access_status == UserAccessStatus.APPROVED
    assert event.after_access_status == UserAccessStatus.BLOCKED


@pytest.mark.asyncio
async def test_noop_transition_creates_no_event(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900041,
        role=UserRole.ADMIN,
    )
    user, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900042,
    )

    _, event = await update_user_access(
        warehouse_db,
        actor_user_id=admin.id,
        target_user_id=user.id,
        access_status=UserAccessStatus.APPROVED,
        recovery_telegram_user_id=900041,
    )

    assert event is None

    count = await warehouse_db.scalar(
        select(text("count(*)"))
        .select_from(UserAccessEvent)
        .where(UserAccessEvent.target_user_id == user.id)
    )
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("before_status", "after_status"),
    [
        ("INVALID", "BLOCKED"),
        ("APPROVED", "INVALID"),
    ],
)
async def test_access_event_statuses_are_database_constrained(
    warehouse_db: AsyncSession,
    before_status: str,
    after_status: str,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900045,
        role=UserRole.ADMIN,
    )
    user, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900046,
    )

    nested = await warehouse_db.begin_nested()

    with pytest.raises(DBAPIError):
        await warehouse_db.execute(
            text(
                """
                INSERT INTO user_access_events (
                    id,
                    actor_user_id,
                    target_user_id,
                    before_access_status,
                    after_access_status,
                    occurred_at
                )
                VALUES (
                    :id,
                    :actor,
                    :target,
                    :before_status,
                    :after_status,
                    :occurred_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "actor": admin.id,
                "target": user.id,
                "before_status": before_status,
                "after_status": after_status,
                "occurred_at": datetime.now(UTC),
            },
        )

    await nested.rollback()


@pytest.mark.asyncio
async def test_access_event_is_database_append_only(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900051,
        role=UserRole.ADMIN,
    )
    user, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900052,
    )

    _, event = await update_user_access(
        warehouse_db,
        actor_user_id=admin.id,
        target_user_id=user.id,
        access_status=UserAccessStatus.BLOCKED,
        recovery_telegram_user_id=900051,
    )
    assert event is not None

    nested = await warehouse_db.begin_nested()

    with pytest.raises(DBAPIError):
        await warehouse_db.execute(
            update(UserAccessEvent)
            .where(UserAccessEvent.id == event.id)
            .values(
                after_access_status=UserAccessStatus.APPROVED
            )
        )

    await nested.rollback()

    nested = await warehouse_db.begin_nested()

    with pytest.raises(DBAPIError):
        await warehouse_db.execute(
            delete(UserAccessEvent).where(
                UserAccessEvent.id == event.id
            )
        )

    await nested.rollback()

    nested = await warehouse_db.begin_nested()

    with pytest.raises(DBAPIError):
        await warehouse_db.execute(
            text("TRUNCATE TABLE user_access_events")
        )

    await nested.rollback()
