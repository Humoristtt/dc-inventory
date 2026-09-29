from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    UserAccessEvent,
)
from app.modules.notifications.models import NotificationOutbox
from app.modules.telegram_bot.service import (
    TelegramAccessManagerAuthorizationError,
    access_callback_data,
    apply_access_decision,
    create_access_decision_callbacks,
)
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


async def _http_app(
    db: AsyncSession,
    settings: Settings,
) -> FastAPI:
    app = create_app(settings)
    connection = await db.connection()

    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(
            connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as request_db:
            yield request_db

    app.dependency_overrides[get_db_session] = session
    return app


async def _identity(
    db: AsyncSession,
    user_id: UUID,
) -> TelegramIdentity:
    identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.user_id == user_id
        )
    )
    assert identity is not None
    return identity


@pytest.mark.parametrize("transport", ["http", "telegram"])
@pytest.mark.parametrize(
    ("actor_role", "target_role", "allowed"),
    [
        (UserRole.ADMIN, UserRole.ADMIN, False),
        (UserRole.OWNER, UserRole.ADMIN, True),
        (UserRole.ADMIN, UserRole.ENGINEER, True),
    ],
)
async def test_access_decision_transport_parity(
    warehouse_db: AsyncSession,
    transport: str,
    actor_role: UserRole,
    target_role: UserRole,
    allowed: bool,
) -> None:
    db = warehouse_db
    manager, token = await actor(
        db,
        actor_role,
        UserAccessStatus.APPROVED,
    )
    target, _ = await actor(
        db,
        target_role,
        UserAccessStatus.PENDING,
    )
    manager_identity = await _identity(db, manager.id)

    access_request = AccessRequest(
        user_id=target.id,
        status=AccessRequestStatus.PENDING,
    )
    db.add(access_request)
    await db.flush()

    settings = Settings(
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
        admin_telegram_user_id=None,
    )

    event_count_before = int(
        await db.scalar(
            select(func.count()).select_from(UserAccessEvent)
        )
        or 0
    )
    outbox_count_before = int(
        await db.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
        or 0
    )

    if transport == "http":
        app = await _http_app(db, settings)
        headers = {
            "Cookie": f"{settings.auth_cookie_name}={token}",
            "Origin": settings.telegram_web_app_url,
        }
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/api/admin/users/{target.id}/access-request-decision",
                headers=headers,
                json={"decision": "APPROVE"},
            )

        if allowed:
            assert response.status_code == 200, response.text
            assert response.json()["access_status"] == "APPROVED"
        else:
            assert response.status_code == 403, response.text
            assert response.json()["detail"]["code"] == "admin_user_forbidden"

    else:
        approve, _ = await create_access_decision_callbacks(
            db,
            access_request.id,
        )
        callback_data = access_callback_data(approve.token)

        if allowed:
            result = await apply_access_decision(
                db,
                callback_data=callback_data,
                callback_query_id="transport-parity",
                actor_telegram_user_id=manager_identity.telegram_user_id,
                message_chat_id=manager_identity.telegram_user_id,
                message_id=1,
                settings=settings,
            )
            assert result.changed is True
            assert result.status == AccessRequestStatus.APPROVED
        else:
            with pytest.raises(
                TelegramAccessManagerAuthorizationError,
                match="only owner may manage administrator access",
            ):
                await apply_access_decision(
                    db,
                    callback_data=callback_data,
                    callback_query_id="transport-parity-denied",
                    actor_telegram_user_id=manager_identity.telegram_user_id,
                    message_chat_id=manager_identity.telegram_user_id,
                    message_id=1,
                    settings=settings,
                )

    await db.refresh(target)
    await db.refresh(access_request)

    event_count_after = int(
        await db.scalar(
            select(func.count()).select_from(UserAccessEvent)
        )
        or 0
    )
    outbox_count_after = int(
        await db.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
        or 0
    )

    if allowed:
        assert target.access_status == UserAccessStatus.APPROVED
        assert access_request.status == AccessRequestStatus.APPROVED
        assert access_request.decided_by_user_id == manager.id
        assert event_count_after == event_count_before + 1
        assert outbox_count_after > outbox_count_before
    else:
        assert target.access_status == UserAccessStatus.PENDING
        assert access_request.status == AccessRequestStatus.PENDING
        assert access_request.decided_by_user_id is None
        assert event_count_after == event_count_before
        assert outbox_count_after == outbox_count_before
