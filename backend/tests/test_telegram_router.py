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


async def test_webhook_stops_reading_when_stream_exceeds_limit() -> None:
    from types import SimpleNamespace
    from typing import Any, cast

    from fastapi import HTTPException

    from app.modules.telegram_bot.api import MAX_TELEGRAM_UPDATE_BYTES, telegram_webhook

    async def stream() -> Any:
        yield b"x" * MAX_TELEGRAM_UPDATE_BYTES
        yield b"x"
        raise AssertionError("oversized request must not be fully buffered")

    request = SimpleNamespace(
        stream=stream,
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(
            telegram_webhook_secret_value="synthetic-secret"))),
    )
    with pytest.raises(HTTPException) as error:
        await telegram_webhook(cast(Any, request), cast(Any, None), "synthetic-secret")
    assert error.value.status_code == 413
