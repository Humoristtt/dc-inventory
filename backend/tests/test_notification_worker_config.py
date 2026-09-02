from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.notifications.worker import (
    configured_gateway_client,
    validate_notification_worker_config,
)

DATABASE_URL = (
    "postgresql+asyncpg://dc_inventory:test@postgres:5432/"
    "dc_inventory"
)


def settings_for(
    *,
    app_env: str = "production",
    gateway_url: str | None = "https://gateway.example.test",
    gateway_secret: str | None = "test-gateway-secret",
) -> Settings:
    return Settings(
        app_env=app_env,
        database_url=DATABASE_URL,
        telegram_gateway_url=gateway_url,
        telegram_gateway_secret=gateway_secret,
        telegram_gateway_timeout_seconds=10,
        notification_worker_claim_ttl_seconds=60,
    )


def test_production_gateway_https_is_accepted() -> None:
    settings = settings_for()

    validate_notification_worker_config(settings)

    client = configured_gateway_client(settings)
    assert client.base_url == "https://gateway.example.test"


@pytest.mark.parametrize(
    "gateway_url",
    [
        "http://gateway.example.test",
        "ftp://gateway.example.test",
        "https://user:password@gateway.example.test",
        "https://gateway.example.test?secret=query",
        "https://gateway.example.test/#fragment",
        " https://gateway.example.test ",
        "https://",
        "not-a-url",
    ],
)
def test_production_gateway_rejects_unsafe_url(
    gateway_url: str,
) -> None:
    settings = settings_for(gateway_url=gateway_url)

    with pytest.raises(
        RuntimeError,
        match="TELEGRAM_GATEWAY_URL",
    ):
        validate_notification_worker_config(settings)


def test_development_gateway_may_use_http() -> None:
    settings = settings_for(
        app_env="development",
        gateway_url="http://telegram-gateway:8787",
    )

    validate_notification_worker_config(settings)


@pytest.mark.parametrize(
    ("gateway_url", "gateway_secret"),
    [
        (None, "secret"),
        ("", "secret"),
        ("https://gateway.example.test", None),
        ("https://gateway.example.test", ""),
    ],
)
def test_gateway_configuration_is_required(
    gateway_url: str | None,
    gateway_secret: str | None,
) -> None:
    settings = settings_for(
        gateway_url=gateway_url,
        gateway_secret=gateway_secret,
    )

    with pytest.raises(
        RuntimeError,
        match="Telegram gateway is not configured",
    ):
        validate_notification_worker_config(settings)


def test_full_config_validation_keeps_lease_guard() -> None:
    settings = Settings(
        app_env="production",
        database_url=DATABASE_URL,
        telegram_gateway_url="https://gateway.example.test",
        telegram_gateway_secret="secret",
        telegram_gateway_timeout_seconds=30,
        notification_worker_claim_ttl_seconds=60,
    )

    with pytest.raises(
        RuntimeError,
        match="NOTIFICATION_WORKER_CLAIM_TTL_SECONDS",
    ):
        validate_notification_worker_config(settings)
