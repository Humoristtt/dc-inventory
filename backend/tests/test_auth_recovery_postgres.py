import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import Settings
from app.modules.auth.dependencies import get_authenticated_context
from app.modules.auth.models import AuthSession
from app.modules.auth.service import (
    RecoveryOwnerConflictError,
    hash_session_token,
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

async def test_existing_cookie_session_promotes_historical_recovery_admin(
    warehouse_db: AsyncSession,
) -> None:
    telegram_user_id = 902041
    user = await _existing_identity(
        warehouse_db,
        telegram_user_id=telegram_user_id,
        role=UserRole.ADMIN,
    )
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        admin_telegram_user_id=telegram_user_id,
    )

    raw_token = "historical-recovery-session"
    current_time = datetime.now(UTC)

    warehouse_db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            created_at=current_time - timedelta(minutes=1),
            expires_at=current_time + timedelta(hours=1),
        )
    )
    await warehouse_db.flush()

    app = SimpleNamespace(
        state=SimpleNamespace(settings=settings)
    )
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/auth/me",
            "raw_path": b"/api/auth/me",
            "query_string": b"",
            "headers": [
                (
                    b"cookie",
                    (
                        f"{settings.auth_cookie_name}="
                        f"{raw_token}"
                    ).encode(),
                )
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("app.spik-inventory.ru", 443),
            "app": app,
        }
    )

    context = await get_authenticated_context(
        request,
        warehouse_db,
    )

    assert context.user.id == user.id
    assert context.user.role == UserRole.OWNER
    assert context.user.access_status == UserAccessStatus.APPROVED

    first_count = await warehouse_db.scalar(
        select(func.count(UserRoleEvent.id)).where(
            UserRoleEvent.target_user_id == user.id
        )
    )
    assert first_count == 1

    context_again = await get_authenticated_context(
        request,
        warehouse_db,
    )

    assert context_again.user.role == UserRole.OWNER

    second_count = await warehouse_db.scalar(
        select(func.count(UserRoleEvent.id)).where(
            UserRoleEvent.target_user_id == user.id
        )
    )
    assert second_count == 1
