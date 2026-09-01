import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.modules.auth.dependencies import get_admin_context, get_approved_context
from app.modules.auth.models import AuthSession
from app.modules.auth.service import AuthenticatedContext
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User


def _context(
    *,
    access_status: UserAccessStatus,
    role: UserRole = UserRole.USER,
) -> AuthenticatedContext:
    now = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
    user = User(id=uuid.uuid4(), role=role, access_status=access_status)
    identity = TelegramIdentity(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        telegram_user_id=123456789,
        first_name="Test",
    )
    auth_session = AuthSession(
        id=uuid.uuid4(),
        user=user,
        user_id=user.id,
        token_hash=b"x" * 32,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )
    return AuthenticatedContext(
        session=auth_session,
        user=user,
        identity=identity,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "access_status",
    [
        UserAccessStatus.PENDING,
        UserAccessStatus.REJECTED,
        UserAccessStatus.BLOCKED,
    ],
)
async def test_approved_dependency_rejects_unapproved_users(
    access_status: UserAccessStatus,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_approved_context(_context(access_status=access_status))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "access approval required"


@pytest.mark.asyncio
async def test_approved_dependency_accepts_approved_user() -> None:
    context = _context(access_status=UserAccessStatus.APPROVED)
    assert await get_approved_context(context) is context


@pytest.mark.asyncio
async def test_admin_dependency_rejects_regular_approved_user() -> None:
    context = _context(access_status=UserAccessStatus.APPROVED)

    with pytest.raises(HTTPException) as exc_info:
        await get_admin_context(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "administrator role required"


@pytest.mark.asyncio
async def test_admin_dependency_accepts_approved_admin() -> None:
    context = _context(
        access_status=UserAccessStatus.APPROVED,
        role=UserRole.ADMIN,
    )
    assert await get_admin_context(context) is context
