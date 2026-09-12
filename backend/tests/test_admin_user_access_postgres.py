from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuthSession
from app.modules.identity.admin_service import (
    AdminUserForbiddenError,
    InvalidAccessTransitionError,
    OutstandingCustodyInvariantError,
    RecoveryAdminInvariantError,
    update_user_access,
    update_user_role,
)
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import (
    TelegramIdentity,
    User,
    UserAccessEvent,
    UserRoleEvent,
)
from app.modules.inventory.models import UserItemCustodyBalance
from tests.warehouse_helpers import scenario


async def _create_user(
    warehouse_db: AsyncSession,
    *,
    telegram_user_id: int,
    role: UserRole = UserRole.ENGINEER,
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
async def test_admin_cannot_block_another_admin(
    warehouse_db: AsyncSession,
) -> None:
    actor, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900035,
        role=UserRole.ADMIN,
    )
    target, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900034,
        role=UserRole.ADMIN,
    )

    with pytest.raises(AdminUserForbiddenError):
        await update_user_access(
            warehouse_db,
            actor_user_id=actor.id,
            target_user_id=target.id,
            access_status=UserAccessStatus.BLOCKED,
            recovery_telegram_user_id=None,
        )


@pytest.mark.asyncio
async def test_owner_can_block_admin(
    warehouse_db: AsyncSession,
) -> None:
    actor, _ = await _create_user(
        warehouse_db,
        telegram_user_id=900036,
        role=UserRole.OWNER,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        UserRole.ENGINEER,
        UserRole.SENIOR_ENGINEER,
        UserRole.MANAGER,
    ],
)
async def test_admin_can_assign_standard_roles(
    warehouse_db: AsyncSession,
    role: UserRole,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901001,
        role=UserRole.ADMIN,
    )
    target, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901002,
        role=(
            UserRole.SENIOR_ENGINEER
            if role == UserRole.ENGINEER
            else UserRole.ENGINEER
        ),
    )

    changed, event = await update_user_role(
        warehouse_db,
        actor_user_id=admin.id,
        target_user_id=target.id,
        role=role,
        recovery_telegram_user_id=None,
    )

    assert changed.role == role
    assert event is not None
    assert event.before_role != event.after_role


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.OWNER])
async def test_admin_cannot_assign_privileged_roles(
    warehouse_db: AsyncSession,
    role: UserRole,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901011,
        role=UserRole.ADMIN,
    )
    target, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901012,
    )

    with pytest.raises(AdminUserForbiddenError):
        await update_user_role(
            warehouse_db,
            actor_user_id=admin.id,
            target_user_id=target.id,
            role=role,
            recovery_telegram_user_id=None,
        )


@pytest.mark.asyncio
async def test_admin_cannot_change_admin_or_owner_role(
    warehouse_db: AsyncSession,
) -> None:
    admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901021,
        role=UserRole.ADMIN,
    )
    other_admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901022,
        role=UserRole.ADMIN,
    )
    owner, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901023,
        role=UserRole.OWNER,
    )

    for target in (other_admin, owner):
        with pytest.raises((AdminUserForbiddenError, RecoveryAdminInvariantError)):
            await update_user_role(
                warehouse_db,
                actor_user_id=admin.id,
                target_user_id=target.id,
                role=UserRole.ENGINEER,
                recovery_telegram_user_id=None,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.ENGINEER, UserRole.MANAGER, UserRole.ADMIN])
async def test_owner_can_assign_non_owner_roles(
    warehouse_db: AsyncSession,
    role: UserRole,
) -> None:
    owner, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901031,
        role=UserRole.OWNER,
    )
    target, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901032,
        role=UserRole.SENIOR_ENGINEER,
    )

    changed, event = await update_user_role(
        warehouse_db,
        actor_user_id=owner.id,
        target_user_id=target.id,
        role=role,
        recovery_telegram_user_id=901031,
    )

    assert changed.role == role
    assert event is not None


@pytest.mark.asyncio
async def test_self_role_mutation_and_recovery_identity_are_immutable(
    warehouse_db: AsyncSession,
) -> None:
    owner, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901041,
        role=UserRole.OWNER,
    )
    historical_recovery_admin, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901042,
        role=UserRole.ADMIN,
    )

    with pytest.raises(AdminUserForbiddenError, match="self role"):
        await update_user_role(
            warehouse_db,
            actor_user_id=owner.id,
            target_user_id=owner.id,
            role=UserRole.ADMIN,
            recovery_telegram_user_id=901041,
        )

    with pytest.raises(RecoveryAdminInvariantError):
        await update_user_role(
            warehouse_db,
            actor_user_id=owner.id,
            target_user_id=historical_recovery_admin.id,
            role=UserRole.ENGINEER,
            recovery_telegram_user_id=901042,
        )


@pytest.mark.asyncio
async def test_role_noop_creates_no_event_and_change_creates_exactly_one(
    warehouse_db: AsyncSession,
) -> None:
    owner, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901051,
        role=UserRole.OWNER,
    )
    target, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901052,
    )

    _, no_event = await update_user_role(
        warehouse_db,
        actor_user_id=owner.id,
        target_user_id=target.id,
        role=UserRole.ENGINEER,
        recovery_telegram_user_id=901051,
    )
    assert no_event is None

    _, event = await update_user_role(
        warehouse_db,
        actor_user_id=owner.id,
        target_user_id=target.id,
        role=UserRole.SENIOR_ENGINEER,
        recovery_telegram_user_id=901051,
    )
    assert event is not None
    assert await warehouse_db.scalar(
        select(text("count(*)"))
        .select_from(UserRoleEvent)
        .where(UserRoleEvent.target_user_id == target.id)
    ) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.ADMIN])
async def test_outstanding_custody_blocks_non_custody_role_transition(
    warehouse_db: AsyncSession,
    role: UserRole,
) -> None:
    target_id, item_id, _source, _destination = await scenario(
        warehouse_db,
        UserRole.ENGINEER,
    )
    owner, _ = await _create_user(
        warehouse_db,
        telegram_user_id=901061,
        role=UserRole.OWNER,
    )
    warehouse_db.add(
        UserItemCustodyBalance(
            user_id=target_id,
            item_id=item_id,
            quantity=1,
        )
    )
    await warehouse_db.flush()

    with pytest.raises(OutstandingCustodyInvariantError):
        await update_user_role(
            warehouse_db,
            actor_user_id=owner.id,
            target_user_id=target_id,
            role=role,
            recovery_telegram_user_id=901061,
        )
