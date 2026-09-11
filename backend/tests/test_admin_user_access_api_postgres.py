from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


async def _api_context(
    db: AsyncSession,
) -> tuple[
    FastAPI,
    dict[str, tuple[str, dict[str, str]]],
    int,
]:
    admin, admin_token = await actor(
        db,
        UserRole.ADMIN,
        UserAccessStatus.APPROVED,
    )
    user, user_token = await actor(
        db,
        UserRole.ENGINEER,
        UserAccessStatus.APPROVED,
    )

    admin_identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.user_id == admin.id
        )
    )
    assert admin_identity is not None

    settings = Settings(
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
        admin_telegram_user_id=admin_identity.telegram_user_id,
    )
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

    headers = {
        "admin": (
            str(admin.id),
            {
                "Cookie": (
                    f"{settings.auth_cookie_name}={admin_token}"
                ),
                "Origin": settings.telegram_web_app_url,
            },
        ),
        "user": (
            str(user.id),
            {
                "Cookie": (
                    f"{settings.auth_cookie_name}={user_token}"
                ),
                "Origin": settings.telegram_web_app_url,
            },
        ),
    }

    return app, headers, admin_identity.telegram_user_id


async def test_admin_user_access_api_security(
    warehouse_db: AsyncSession,
) -> None:
    app, users, _ = await _api_context(warehouse_db)

    admin_id, admin_headers = users["admin"]
    user_id, user_headers = users["user"]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauthenticated = await client.get(
            "/api/admin/users"
        )
        assert unauthenticated.status_code == 401

        regular_user = await client.get(
            "/api/admin/users",
            headers=user_headers,
        )
        assert regular_user.status_code == 403

        admin_list = await client.get(
            "/api/admin/users",
            headers=admin_headers,
        )
        assert admin_list.status_code == 200, admin_list.text
        assert admin_list.headers["cache-control"] == "no-store"

        body = admin_list.json()
        assert body["total"] >= 2

        ids = {
            row["id"]
            for row in body["items"]
        }
        assert admin_id in ids
        assert user_id in ids

        bad_origin_headers = dict(admin_headers)
        bad_origin_headers["Origin"] = "https://evil.example"

        bad_origin = await client.patch(
            f"/api/admin/users/{user_id}",
            headers=bad_origin_headers,
            json={
                "access_status": "BLOCKED",
            },
        )
        assert bad_origin.status_code == 403

        block_user = await client.patch(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
            json={
                "access_status": "BLOCKED",
            },
        )
        assert block_user.status_code == 200, block_user.text
        assert block_user.headers["cache-control"] == "no-store"
        assert block_user.json()["access_status"] == "BLOCKED"
        assert block_user.json()["role"] == "ENGINEER"

        old_user_session = await client.get(
            "/api/admin/users",
            headers=user_headers,
        )
        assert old_user_session.status_code == 401

        events = await client.get(
            f"/api/admin/users/{user_id}/events",
            headers=admin_headers,
        )
        assert events.status_code == 200, events.text
        assert events.headers["cache-control"] == "no-store"

        event_body = events.json()
        assert event_body["total"] == 1
        assert len(event_body["items"]) == 1
        assert (
            event_body["items"][0]["before_access_status"]
            == "APPROVED"
        )
        assert (
            event_body["items"][0]["after_access_status"]
            == "BLOCKED"
        )

        recovery_block = await client.patch(
            f"/api/admin/users/{admin_id}",
            headers=admin_headers,
            json={
                "access_status": "BLOCKED",
            },
        )
        assert recovery_block.status_code == 409
        assert "owner/recovery identity" in recovery_block.json()["detail"]


async def test_admin_can_unblock_user_via_api(
    warehouse_db: AsyncSession,
) -> None:
    app, users, _ = await _api_context(warehouse_db)

    _, admin_headers = users["admin"]
    user_id, _ = users["user"]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        blocked = await client.patch(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
            json={
                "access_status": "BLOCKED",
            },
        )
        assert blocked.status_code == 200, blocked.text

        unblocked = await client.patch(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
            json={
                "access_status": "APPROVED",
            },
        )
        assert unblocked.status_code == 200, unblocked.text
        assert unblocked.json()["access_status"] == "APPROVED"

        events = await client.get(
            f"/api/admin/users/{user_id}/events",
            headers=admin_headers,
        )
        assert events.status_code == 200
        assert events.json()["total"] == 2

        states = [
            (
                event["before_access_status"],
                event["after_access_status"],
            )
            for event in events.json()["items"]
        ]
        assert (
            "BLOCKED",
            "APPROVED",
        ) in states
        assert (
            "APPROVED",
            "BLOCKED",
        ) in states


async def test_admin_user_access_rejects_workflow_bypass(
    warehouse_db: AsyncSession,
) -> None:
    app, users, _ = await _api_context(warehouse_db)

    _, admin_headers = users["admin"]

    pending, _ = await actor(
        warehouse_db,
        UserRole.ENGINEER,
        UserAccessStatus.PENDING,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            f"/api/admin/users/{pending.id}",
            headers=admin_headers,
            json={
                "access_status": "BLOCKED",
            },
        )

    assert response.status_code == 409
    assert "access-request workflow" in response.json()["detail"]
