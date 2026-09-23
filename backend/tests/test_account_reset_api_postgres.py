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
from app.modules.identity.enums import UserRole
from app.modules.identity.models import TelegramIdentity
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


async def _setup(
    db: AsyncSession,
) -> tuple[FastAPI, str, dict[str, str], dict[str, str], int]:
    admin, admin_token = await actor(db, UserRole.ADMIN)
    target, target_token = await actor(db, UserRole.ENGINEER)
    identity = await db.scalar(
        select(TelegramIdentity).where(TelegramIdentity.user_id == target.id)
    )
    assert identity is not None
    settings = Settings(
        app_env="test",
        telegram_web_app_url="https://app.spik-inventory.ru",
        admin_telegram_user_id=None,
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

    def headers(token: str) -> dict[str, str]:
        return {
            "Cookie": f"{settings.auth_cookie_name}={token}",
            "Origin": settings.telegram_web_app_url,
        }

    return (
        app,
        str(target.id),
        headers(admin_token),
        headers(target_token),
        identity.telegram_user_id,
    )


async def test_reset_endpoint_security_and_confirmed_re_registration(
    warehouse_db: AsyncSession,
) -> None:
    app, target_id, admin_headers, target_headers, telegram_id = await _setup(
        warehouse_db
    )
    endpoint = f"/api/admin/users/{target_id}/reset"
    payload = {"telegram_user_id": telegram_id, "confirmation": "СБРОСИТЬ"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post(endpoint, json=payload)).status_code == 401
        assert (
            await client.post(endpoint, headers=target_headers, json=payload)
        ).status_code == 403
        invalid_origin = dict(admin_headers, Origin="https://evil.example")
        assert (
            await client.post(endpoint, headers=invalid_origin, json=payload)
        ).status_code == 403
        assert (
            await client.post(
                endpoint,
                headers=admin_headers,
                json={"telegram_user_id": telegram_id, "confirmation": "wrong"},
            )
        ).status_code == 422

        mismatch = await client.post(
            endpoint,
            headers=admin_headers,
            json={"telegram_user_id": telegram_id + 1, "confirmation": "СБРОСИТЬ"},
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"]["code"] == "admin_user_reset_identity_mismatch"

        reset = await client.post(endpoint, headers=admin_headers, json=payload)
        assert reset.status_code == 204, reset.text
        assert reset.headers["cache-control"] == "no-store"

        old_session = await client.get("/api/access-requests/me", headers=target_headers)
        assert old_session.status_code == 401

        users = await client.get("/api/admin/users", headers=admin_headers)
        assert users.status_code == 200, users.text
        assert target_id not in {row["id"] for row in users.json()["items"]}

        repeated = await client.post(endpoint, headers=admin_headers, json=payload)
        assert repeated.status_code == 404
