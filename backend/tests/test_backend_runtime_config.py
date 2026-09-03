from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import create_app, validate_backend_runtime_config

DATABASE_URL = (
    "postgresql+asyncpg://dc_inventory:test@postgres:5432/"
    "dc_inventory"
)


def production_settings(
    **overrides: object,
) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "database_url": DATABASE_URL,
        "telegram_bot_token": "123456789:test-token",
        "admin_telegram_user_id": 123456789,
        "telegram_webhook_secret": "webhook-secret",
        "telegram_web_app_url": (
            "https://app.spik-inventory.ru"
        ),
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_valid_production_backend_config_is_accepted() -> None:
    settings = production_settings()

    validate_backend_runtime_config(settings)

    app = create_app(settings)
    assert app.state.settings is settings


@pytest.mark.parametrize(
    ("field", "value", "expected_name"),
    [
        ("telegram_bot_token", None, "TELEGRAM_BOT_TOKEN"),
        (
            "telegram_bot_token",
            "   ",
            "TELEGRAM_BOT_TOKEN",
        ),
        (
            "admin_telegram_user_id",
            None,
            "ADMIN_TELEGRAM_USER_ID",
        ),
        (
            "telegram_webhook_secret",
            None,
            "TELEGRAM_WEBHOOK_SECRET",
        ),
        (
            "telegram_webhook_secret",
            "   ",
            "TELEGRAM_WEBHOOK_SECRET",
        ),
    ],
)
def test_production_backend_rejects_missing_telegram_config(
    field: str,
    value: object,
    expected_name: str,
) -> None:
    settings = production_settings(**{field: value})

    with pytest.raises(
        RuntimeError,
        match=expected_name,
    ):
        create_app(settings)


def test_missing_fields_are_reported_together() -> None:
    settings = production_settings(
        telegram_bot_token=None,
        admin_telegram_user_id=None,
        telegram_webhook_secret=None,
    )

    with pytest.raises(RuntimeError) as exc_info:
        create_app(settings)

    message = str(exc_info.value)

    assert "TELEGRAM_BOT_TOKEN" in message
    assert "ADMIN_TELEGRAM_USER_ID" in message
    assert "TELEGRAM_WEBHOOK_SECRET" in message


@pytest.mark.parametrize(
    "url",
    [
        "http://app.spik-inventory.ru",
        "app.spik-inventory.ru",
        "https://",
        "https://user:pass@example.com/app",
        "https://example.com/app",
        "https://example.com/?source=telegram",
        "https://example.com/app?source=telegram",
        "https://example.com/app#fragment",
        " https://example.com/app ",
        "https://example.com:99999/app",
    ],
)
def test_production_backend_rejects_invalid_web_app_url(
    url: str,
) -> None:
    settings = production_settings(
        telegram_web_app_url=url,
    )

    with pytest.raises(
        RuntimeError,
        match="TELEGRAM_WEB_APP_URL",
    ):
        create_app(settings)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://example.com/",
        "https://example.com:8443",
    ],
)
def test_production_backend_accepts_https_web_app_origin(
    url: str,
) -> None:
    settings = production_settings(
        telegram_web_app_url=url,
    )

    validate_backend_runtime_config(settings)


def test_non_production_backend_does_not_require_telegram_runtime() -> None:
    settings = Settings(
        app_env="test",
        database_url=DATABASE_URL,
        telegram_web_app_url="http://localhost:5173",
    )

    validate_backend_runtime_config(settings)
    app = create_app(settings)

    assert app.docs_url == "/api/docs"
