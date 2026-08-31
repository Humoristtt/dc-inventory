import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.models import AuthSession
from app.modules.auth.service import (
    hash_session_token,
    issue_auth_session,
    load_auth_context,
    revoke_auth_session,
    upsert_telegram_identity,
)
from app.modules.auth.telegram import TelegramWebAppUser, ValidatedTelegramInitData
from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus, UserRole
from app.modules.identity.models import AccessRequest, TelegramIdentity, User

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"
NOW = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)


def _validated(telegram_user_id: int = 42424242) -> ValidatedTelegramInitData:
    return ValidatedTelegramInitData(
        user=TelegramWebAppUser(
            id=telegram_user_id,
            first_name="Иван",
            last_name="Иванов",
            username="ivanov",
            language_code="ru",
        ),
        auth_date=NOW,
        query_id="query-id",
    )


@pytest.mark.asyncio
async def test_new_telegram_identity_starts_pending() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    settings = Settings(database_url=DATABASE_URL)

    user, identity = await upsert_telegram_identity(db, _validated(), settings, now=NOW)

    assert user.role == UserRole.USER
    assert user.access_status == UserAccessStatus.PENDING
    assert identity.telegram_user_id == 42424242
    assert identity.username == "ivanov"
    assert identity.last_auth_at == NOW
    assert db.add.call_count == 2
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_identity_profile_is_refreshed() -> None:
    user = User(
        id=uuid.uuid4(),
        role=UserRole.USER,
        access_status=UserAccessStatus.PENDING,
    )
    identity = TelegramIdentity(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        telegram_user_id=42424242,
        username="old",
        first_name="Old",
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = identity
    settings = Settings(database_url=DATABASE_URL)

    returned_user, returned_identity = await upsert_telegram_identity(
        db,
        _validated(),
        settings,
        now=NOW,
    )

    assert returned_user is user
    assert returned_identity is identity
    assert identity.username == "ivanov"
    assert identity.first_name == "Иван"
    assert identity.last_name == "Иванов"
    assert identity.language_code == "ru"
    assert identity.last_auth_at == NOW


@pytest.mark.asyncio
async def test_bootstrap_admin_recovery_resolves_existing_pending_request() -> None:
    user = User(
        id=uuid.uuid4(),
        role=UserRole.USER,
        access_status=UserAccessStatus.PENDING,
    )
    identity = TelegramIdentity(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        telegram_user_id=42424242,
        first_name="Иван",
    )
    pending = AccessRequest(
        id=uuid.uuid4(),
        user_id=user.id,
        status=AccessRequestStatus.PENDING,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = identity
    pending_result = MagicMock()
    pending_result.first.return_value = pending
    db.scalars.return_value = pending_result
    settings = Settings(
        database_url=DATABASE_URL,
        admin_telegram_user_id=42424242,
    )

    await upsert_telegram_identity(db, _validated(), settings, now=NOW)

    assert user.role == UserRole.ADMIN
    assert user.access_status == UserAccessStatus.APPROVED
    assert user.approved_at == NOW
    assert pending.status == AccessRequestStatus.APPROVED
    assert pending.decided_at == NOW
    assert pending.decided_by_user_id == user.id
    assert pending.decision_note == "bootstrap admin configuration"


@pytest.mark.asyncio
async def test_issue_auth_session_stores_only_token_hash() -> None:
    user = User(id=uuid.uuid4())
    db = AsyncMock(spec=AsyncSession)

    issued = await issue_auth_session(db, user, ttl_seconds=3600, now=NOW)

    assert issued.raw_token
    assert issued.session.user_id == user.id
    assert issued.session.token_hash == hash_session_token(issued.raw_token)
    assert issued.raw_token.encode() != issued.session.token_hash
    assert issued.session.created_at == NOW
    assert issued.session.expires_at == NOW + timedelta(hours=1)
    db.add.assert_called_once_with(issued.session)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_auth_context_returns_loaded_identity() -> None:
    user = User(id=uuid.uuid4(), access_status=UserAccessStatus.APPROVED)
    identity = TelegramIdentity(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        telegram_user_id=42424242,
        first_name="Иван",
    )
    user.telegram_identity = identity
    auth_session = AuthSession(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        token_hash=hash_session_token("raw-token"),
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = auth_session

    context = await load_auth_context(db, "raw-token", now=NOW)

    assert context is not None
    assert context.session is auth_session
    assert context.user is user
    assert context.identity is identity


@pytest.mark.asyncio
async def test_load_auth_context_returns_none_when_session_is_not_valid() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = None
    assert await load_auth_context(db, "invalid-token", now=NOW) is None


@pytest.mark.asyncio
async def test_revoke_auth_session_sets_revocation_time() -> None:
    user = User(id=uuid.uuid4())
    auth_session = AuthSession(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        token_hash=b"x" * 32,
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    db = AsyncMock(spec=AsyncSession)

    await revoke_auth_session(db, auth_session, now=NOW + timedelta(minutes=5))

    assert auth_session.revoked_at == NOW + timedelta(minutes=5)
    db.flush.assert_awaited_once()
