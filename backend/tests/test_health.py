from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.health import DatabaseUnavailableError
from app.main import create_app


@pytest.mark.asyncio
async def test_live_healthcheck() -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get("/api/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_healthcheck() -> None:
    app = create_app()
    app.state.db_engine = cast(AsyncEngine, object())
    transport = ASGITransport(app=app)

    with patch(
        "app.api.health.ensure_database_ready",
        new_callable=AsyncMock,
    ):
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_ready_returns_503_when_database_is_unavailable() -> None:
    app = create_app()
    app.state.db_engine = cast(AsyncEngine, object())
    transport = ASGITransport(app=app)

    with patch(
        "app.api.health.ensure_database_ready",
        new_callable=AsyncMock,
        side_effect=DatabaseUnavailableError,
    ):
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
