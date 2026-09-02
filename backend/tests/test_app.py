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
