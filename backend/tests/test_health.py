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


async def test_readiness_checks_schema_even_when_tables_are_empty() -> None:
    from unittest.mock import MagicMock

    from sqlalchemy.exc import ProgrammingError

    from app.db.health import ensure_database_ready

    engine = MagicMock()
    connection = AsyncMock()
    engine.connect.return_value.__aenter__.return_value = connection
    await ensure_database_ready(engine)
    query = str(connection.execute.call_args.args[0])
    assert "WHERE false" in query
    assert "m.journal_seq" in query and "s.expires_at" in query
    assert "m.custody_user_id" in query
    assert "public.user_item_custody_balances c" in query
    assert "c.user_id" in query
    assert "c.item_id" in query
    assert "c.quantity" in query
    assert "public.user_access_events ua" in query
    assert "ua.actor_user_id" in query
    assert "ua.target_user_id" in query
    assert "ua.before_access_status" in query
    assert "ua.after_access_status" in query
    assert "ua.occurred_at" in query
    assert "u.role" in query
    assert "public.user_role_events ur" in query
    assert "ur.actor_user_id" in query
    assert "ur.target_user_id" in query
    assert "ur.before_role" in query
    assert "ur.after_role" in query
    assert "ur.occurred_at" in query
    connection.execute.side_effect = ProgrammingError("sql", {}, Exception("missing column"))
    with pytest.raises(DatabaseUnavailableError):
        await ensure_database_ready(engine)


async def test_database_application_names_are_distinct() -> None:
    from app.core.config import Settings
    from app.db.engine import create_engine
    from app.db.migration_settings import migration_server_settings

    settings = Settings(app_env="test")
    for name in ("dc-inventory-backend", "dc-inventory-telegram-worker",
                 "dc-inventory-maintenance-worker"):
        with patch("app.db.engine.create_async_engine") as factory:
            create_engine(settings, application_name=name)
        server = factory.call_args.kwargs["connect_args"]["server_settings"]
        assert server["application_name"] == name
    assert migration_server_settings(settings)["application_name"] == "dc-inventory-migrations"
