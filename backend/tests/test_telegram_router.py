from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import app, create_app

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"


def test_telegram_webhook_route_is_registered() -> None:
    assert "/api/telegram/webhook" in set(app.openapi()["paths"])


async def _mock_db_session() -> AsyncIterator[AsyncSession]:
    yield AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_wrong_secret() -> None:
    application = create_app(
        Settings(
            database_url=DATABASE_URL,
            telegram_webhook_secret="expected-secret",
        )
    )
    application.dependency_overrides[get_db_session] = _mock_db_session
    transport = ASGITransport(app=application)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/telegram/webhook",
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "wrong-secret",
                },
                json={"update_id": 1},
            )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_telegram_webhook_validates_update_id_before_transaction() -> None:
    application = create_app(
        Settings(
            database_url=DATABASE_URL,
            telegram_webhook_secret="expected-secret",
        )
    )
    application.dependency_overrides[get_db_session] = _mock_db_session
    transport = ASGITransport(app=application)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/telegram/webhook",
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "expected-secret",
                },
                json={"update_id": -1},
            )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 400
