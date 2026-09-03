from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"


def test_api_docs_are_disabled_in_production() -> None:
    app = create_app(
        Settings(
            app_env="production",
            database_url=DATABASE_URL,
            telegram_bot_token="123456789:test-token",
            admin_telegram_user_id=123456789,
            telegram_webhook_secret="webhook-secret",
            telegram_web_app_url="https://app.spik-inventory.ru",
        )
    )

    assert app.docs_url is None
    assert app.openapi_url is None
    assert app.redoc_url is None


def test_api_docs_are_available_outside_production() -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url=DATABASE_URL,
        )
    )

    assert app.docs_url == "/api/docs"
    assert app.openapi_url == "/api/openapi.json"
    assert app.redoc_url is None


async def _host_probe(
    app: FastAPI,
    *,
    base_url: str,
) -> int:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url=base_url,
    ) as client:
        response = await client.get("/__trusted_host_probe__")
    return response.status_code


def _production_app() -> FastAPI:
    return create_app(
        Settings(
            app_env="production",
            database_url=DATABASE_URL,
            telegram_bot_token="123456789:test-token",
            admin_telegram_user_id=123456789,
            telegram_webhook_secret="webhook-secret",
            telegram_web_app_url="https://app.spik-inventory.ru",
        )
    )


def test_production_trusted_hosts_follow_web_app_origin() -> None:
    from app.main import _trusted_hosts

    settings = Settings(
        app_env="production",
        database_url=DATABASE_URL,
        telegram_bot_token="123456789:test-token",
        admin_telegram_user_id=123456789,
        telegram_webhook_secret="webhook-secret",
        telegram_web_app_url="https://APP.SPIK-INVENTORY.RU",
    )

    assert _trusted_hosts(settings) == [
        "app.spik-inventory.ru",
        "127.0.0.1",
        "localhost",
    ]


def test_non_production_trusted_hosts_remain_unrestricted() -> None:
    from app.main import _trusted_hosts

    settings = Settings(
        app_env="test",
        database_url=DATABASE_URL,
    )

    assert _trusted_hosts(settings) == ["*"]


def test_production_rejects_untrusted_host() -> None:
    import asyncio

    status = asyncio.run(
        _host_probe(
            _production_app(),
            base_url="https://evil.example",
        )
    )

    assert status == 400


def test_production_accepts_public_host() -> None:
    import asyncio

    status = asyncio.run(
        _host_probe(
            _production_app(),
            base_url="https://app.spik-inventory.ru",
        )
    )

    assert status == 404


def test_production_accepts_loopback_health_host() -> None:
    import asyncio

    status = asyncio.run(
        _host_probe(
            _production_app(),
            base_url="http://127.0.0.1",
        )
    )

    assert status == 404
