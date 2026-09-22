from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.access.service import create_or_get_access_request
from app.modules.auth.models import AuthSession
from app.modules.auth.service import upsert_telegram_identity
from app.modules.auth.telegram import TelegramWebAppUser, ValidatedTelegramInitData
from app.modules.identity.admin_service import (
    AdminUserForbiddenError,
    OutstandingCustodyInvariantError,
    RecoveryAdminInvariantError,
    get_admin_user,
    list_admin_users,
)
from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus, UserRole
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    User,
    UserAccessEvent,
)
from app.modules.identity.reset_service import reset_user_account
from app.modules.inventory.models import UserItemCustodyBalance
from app.modules.notifications.models import NotificationOutbox
from app.modules.notifications.service import notification_dedupe_key
from app.modules.telegram_bot.models import AccessDecisionCallback
from tests.warehouse_helpers import scenario


async def _user(
    db: AsyncSession,
    telegram_id: int,
    *,
    role: UserRole = UserRole.ENGINEER,
    access: UserAccessStatus = UserAccessStatus.APPROVED,
) -> User:
    user = User(id=uuid.uuid4(), role=role, access_status=access)
    db.add_all(
        [
            user,
            TelegramIdentity(
                user=user,
                telegram_user_id=telegram_id,
                first_name=f"Synthetic {telegram_id}",
            ),
        ]
    )
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_reset_frees_telegram_identity_revokes_sessions_and_preserves_audit(
    warehouse_db: AsyncSession,
) -> None:
    actor = await _user(warehouse_db, 99001001, role=UserRole.ADMIN)
    target = await _user(warehouse_db, 99001002)
    old_id = target.id
    now = datetime.now(UTC)

    session = AuthSession(
        user_id=target.id,
        token_hash=b"r" * 32,
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    old_event = UserAccessEvent(
        actor_user_id=actor.id,
        target_user_id=target.id,
        before_access_status=UserAccessStatus.PENDING,
        after_access_status=UserAccessStatus.APPROVED,
        occurred_at=now,
    )
    warehouse_db.add_all([session, old_event])
    await warehouse_db.flush()

    await reset_user_account(
        warehouse_db,
        actor_user_id=actor.id,
        target_user_id=target.id,
        expected_telegram_user_id=99001002,
        recovery_telegram_user_id=None,
        now=now,
    )

    assert await warehouse_db.scalar(
        select(TelegramIdentity.id).where(
            TelegramIdentity.telegram_user_id == 99001002
        )
    ) is None
    assert session.revoked_at == now or await warehouse_db.scalar(
        select(AuthSession.revoked_at).where(AuthSession.id == session.id)
    ) == now
    assert target.role == UserRole.ENGINEER
    assert target.access_status == UserAccessStatus.BLOCKED
    assert await warehouse_db.scalar(select(User.id).where(User.id == old_id)) == old_id
    assert await warehouse_db.scalar(
        select(func.count(UserAccessEvent.id)).where(
            UserAccessEvent.target_user_id == old_id
        )
    ) == 2

    settings = Settings(
        database_url=os.environ["DATABASE_URL"],
        app_env="test",
        admin_telegram_user_id=None,
    )
    validated = ValidatedTelegramInitData(
        user=TelegramWebAppUser(id=99001002, first_name="Synthetic again"),
        auth_date=now,
        query_id=None,
    )
    new_user, new_identity = await upsert_telegram_identity(
        warehouse_db,
        validated,
        settings,
        now=now,
    )
    assert new_user.id != old_id
    assert new_identity.user_id == new_user.id
    assert new_user.role == UserRole.ENGINEER
    assert new_user.access_status == UserAccessStatus.PENDING

    access = await create_or_get_access_request(warehouse_db, new_user.id)
    assert access.created is True
    assert access.request.status == AccessRequestStatus.PENDING


@pytest.mark.asyncio
async def test_reset_removes_pending_request_and_approval_callbacks(
    warehouse_db: AsyncSession,
) -> None:
    actor = await _user(warehouse_db, 99001011, role=UserRole.ADMIN)
    target = await _user(
        warehouse_db, 99001012, access=UserAccessStatus.PENDING
    )
    request = AccessRequest(user_id=target.id, status=AccessRequestStatus.PENDING)
    warehouse_db.add(request)
    await warehouse_db.flush()
    callback = AccessDecisionCallback(
        token="r" * 26,
        access_request_id=request.id,
        action="APPROVE",
    )
    notification = NotificationOutbox(
        method="sendMessage",
        payload={"chat_id": 99001011, "text": "Synthetic request"},
        dedupe_key=notification_dedupe_key("access-request", request.id, "admin"),
    )
    warehouse_db.add_all([callback, notification])
    await warehouse_db.flush()

    await reset_user_account(
        warehouse_db,
        actor_user_id=actor.id,
        target_user_id=target.id,
        expected_telegram_user_id=99001012,
        recovery_telegram_user_id=None,
    )

    assert await warehouse_db.scalar(
        select(AccessRequest.id).where(AccessRequest.user_id == target.id)
    ) is None
    assert await warehouse_db.scalar(
        select(AccessDecisionCallback.token).where(
            AccessDecisionCallback.access_request_id == request.id
        )
    ) is None
    assert await warehouse_db.scalar(
        select(NotificationOutbox.status).where(
            NotificationOutbox.id == notification.id
        )
    ) == "DEAD"
    assert target.access_status == UserAccessStatus.BLOCKED


@pytest.mark.asyncio
async def test_reset_forbids_self_recovery_and_admin_escalation(
    warehouse_db: AsyncSession,
) -> None:
    actor = await _user(warehouse_db, 99001021, role=UserRole.ADMIN)
    target = await _user(warehouse_db, 99001022, role=UserRole.ADMIN)

    with pytest.raises(AdminUserForbiddenError):
        await reset_user_account(
            warehouse_db,
            actor_user_id=actor.id,
            target_user_id=actor.id,
            expected_telegram_user_id=99001021,
            recovery_telegram_user_id=None,
        )

    with pytest.raises(AdminUserForbiddenError):
        await reset_user_account(
            warehouse_db,
            actor_user_id=actor.id,
            target_user_id=target.id,
            expected_telegram_user_id=99001022,
            recovery_telegram_user_id=None,
        )

    with pytest.raises(RecoveryAdminInvariantError):
        await reset_user_account(
            warehouse_db,
            actor_user_id=actor.id,
            target_user_id=target.id,
            expected_telegram_user_id=99001022,
            recovery_telegram_user_id=99001022,
        )


@pytest.mark.asyncio
async def test_reset_blocks_outstanding_equipment_custody(
    warehouse_db: AsyncSession,
) -> None:
    actor_id, item_id, _, _ = await scenario(warehouse_db)
    target = await _user(warehouse_db, 99001032)
    warehouse_db.add(
        UserItemCustodyBalance(user_id=target.id, item_id=item_id, quantity=1)
    )
    await warehouse_db.flush()

    with pytest.raises(OutstandingCustodyInvariantError):
        await reset_user_account(
            warehouse_db,
            actor_user_id=actor_id,
            target_user_id=target.id,
            expected_telegram_user_id=99001032,
            recovery_telegram_user_id=None,
        )

    assert await warehouse_db.scalar(
        select(TelegramIdentity.telegram_user_id).where(
            TelegramIdentity.user_id == target.id
        )
    ) == 99001032


@pytest.mark.asyncio
async def test_reset_hides_tombstone_from_admin_list(
    warehouse_db: AsyncSession,
) -> None:
    actor = await _user(warehouse_db, 99001041, role=UserRole.ADMIN)
    target = await _user(warehouse_db, 99001042)

    before = await list_admin_users(warehouse_db)
    assert target.id in {user.id for user in before.items}

    await reset_user_account(
        warehouse_db,
        actor_user_id=actor.id,
        target_user_id=target.id,
        expected_telegram_user_id=99001042,
        recovery_telegram_user_id=None,
    )

    after = await list_admin_users(warehouse_db)
    assert target.id not in {user.id for user in after.items}
    assert after.total == before.total - 1
    assert await get_admin_user(warehouse_db, target.id) is None
    assert await warehouse_db.scalar(
        select(User.id).where(User.id == target.id)
    ) == target.id
