import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import Settings
from app.modules.auth.dependencies import (
    _enforce_cookie_mutation_origin,
    get_admin_context,
    get_approved_context,
)
from app.modules.auth.models import AuthSession
from app.modules.auth.service import AuthenticatedContext
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User


def _request(
    method: str,
    *,
    origin: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if origin is not None:
        headers.append((b"origin", origin.encode()))

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("app.spik-inventory.ru", 443),
        }
    )


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

@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_cookie_origin_guard_allows_safe_methods_without_origin(
    method: str,
) -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
    )

    _enforce_cookie_mutation_origin(
        _request(method),
        settings,
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_cookie_origin_guard_rejects_mutation_without_origin(
    method: str,
) -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_cookie_mutation_origin(
            _request(method),
            settings,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "cross-origin authenticated mutation forbidden"
    )


def test_cookie_origin_guard_rejects_foreign_origin() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_cookie_mutation_origin(
            _request(
                "POST",
                origin="https://evil.example",
            ),
            settings,
        )

    assert exc_info.value.status_code == 403


def test_cookie_origin_guard_normalizes_default_https_port() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru:443",
    )

    _enforce_cookie_mutation_origin(
        _request(
            "POST",
            origin="https://app.spik-inventory.ru",
        ),
        settings,
    )


def test_cookie_origin_guard_preserves_non_default_https_port() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru:8443",
    )

    _enforce_cookie_mutation_origin(
        _request(
            "POST",
            origin="https://app.spik-inventory.ru:8443",
        ),
        settings,
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_cookie_mutation_origin(
            _request(
                "POST",
                origin="https://app.spik-inventory.ru",
            ),
            settings,
        )

    assert exc_info.value.status_code == 403


def test_cookie_origin_guard_accepts_configured_origin() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://unused",
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
    )

    _enforce_cookie_mutation_origin(
        _request(
            "PATCH",
            origin="https://app.spik-inventory.ru",
        ),
        settings,
    )
