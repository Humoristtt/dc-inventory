import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.service import (
    RecoveryOwnerConflictError,
    upsert_telegram_identity,
)
from app.modules.auth.telegram import TelegramWebAppUser, ValidatedTelegramInitData
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User, UserRoleEvent

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 9, 12, 12, tzinfo=UTC)


def _validated(telegram_user_id: int) -> ValidatedTelegramInitData:
    return ValidatedTelegramInitData(
        user=TelegramWebAppUser(
            id=telegram_user_id,
            first_name="Recovery",
            username="recovery",
        ),
        auth_date=NOW,
        query_id="recovery-query",
    )


async def _existing_identity(
    db: AsyncSession,
    *,
    telegram_user_id: int,
    role: UserRole,
) -> User:
    user = User(
        id=uuid.uuid4(),
        role=role,
        access_status=UserAccessStatus.APPROVED,
        approved_at=NOW,
    )
    db.add_all(
        [
            user,
            TelegramIdentity(
                user=user,
                telegram_user_id=telegram_user_id,
                first_name="Existing",
            ),
        ]
    )
    await db.flush()
    return user


async def test_fresh_configured_identity_is_owner(
    warehouse_db: AsyncSession,
) -> None:
    telegram_user_id = 902001
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        admin_telegram_user_id=telegram_user_id,
    )

    user, _ = await upsert_telegram_identity(
        warehouse_db,
        _validated(telegram_user_id),
        settings,
        now=NOW,
    )

    assert user.role == UserRole.OWNER
    assert user.access_status == UserAccessStatus.APPROVED


async def test_historical_recovery_admin_promotes_once_with_audit(
    warehouse_db: AsyncSession,
) -> None:
    telegram_user_id = 902011
    user = await _existing_identity(
        warehouse_db,
        telegram_user_id=telegram_user_id,
        role=UserRole.ADMIN,
    )
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        admin_telegram_user_id=telegram_user_id,
    )

    await upsert_telegram_identity(
        warehouse_db,
        _validated(telegram_user_id),
        settings,
        now=NOW,
    )
    await upsert_telegram_identity(
        warehouse_db,
        _validated(telegram_user_id),
        settings,
        now=NOW,
    )

    assert user.role == UserRole.OWNER
    events = (
        await warehouse_db.scalars(
            select(UserRoleEvent).where(UserRoleEvent.target_user_id == user.id)
        )
    ).all()
    assert len(events) == 1
    assert events[0].actor_user_id == user.id
    assert events[0].before_role == UserRole.ADMIN
    assert events[0].after_role == UserRole.OWNER


async def test_non_recovery_admin_remains_admin(
    warehouse_db: AsyncSession,
) -> None:
    user = await _existing_identity(
        warehouse_db,
        telegram_user_id=902021,
        role=UserRole.ADMIN,
    )
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        admin_telegram_user_id=902022,
    )

    await upsert_telegram_identity(
        warehouse_db,
        _validated(902021),
        settings,
        now=NOW,
    )

    assert user.role == UserRole.ADMIN
    assert await warehouse_db.scalar(
        select(func.count(UserRoleEvent.id)).where(
            UserRoleEvent.target_user_id == user.id
        )
    ) == 0


async def test_recovery_owner_collision_fails_closed(
    warehouse_db: AsyncSession,
) -> None:
    owner = await _existing_identity(
        warehouse_db,
        telegram_user_id=902031,
        role=UserRole.OWNER,
    )
    recovery = await _existing_identity(
        warehouse_db,
        telegram_user_id=902032,
        role=UserRole.ADMIN,
    )
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        admin_telegram_user_id=902032,
    )

    with pytest.raises(RecoveryOwnerConflictError):
        await upsert_telegram_identity(
            warehouse_db,
            _validated(902032),
            settings,
            now=NOW,
        )

    assert owner.role == UserRole.OWNER
    assert recovery.role == UserRole.ADMIN
