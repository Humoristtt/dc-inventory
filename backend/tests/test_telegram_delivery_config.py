import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.notifications.worker import configured_gateway_client
from app.modules.telegram_bot.service import (
    access_callback_data,
    parse_access_callback_data,
    verify_webhook_secret,
)

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"


def test_telegram_delivery_defaults() -> None:
    settings = Settings(database_url=DATABASE_URL)

    assert settings.telegram_webhook_secret_value is None
    assert settings.telegram_gateway_url_value is None
    assert settings.telegram_gateway_secret_value is None
    assert settings.telegram_web_app_url == "https://app.spik-inventory.ru"
    assert settings.notification_worker_claim_ttl_seconds == 60


def test_gateway_worker_requires_url_and_secret() -> None:
    with pytest.raises(RuntimeError):
        configured_gateway_client(Settings(database_url=DATABASE_URL))

    client = configured_gateway_client(
        Settings(
            database_url=DATABASE_URL,
            telegram_gateway_url="https://gateway.example/",
            telegram_gateway_secret="gateway-secret",
        )
    )
    assert client.base_url == "https://gateway.example"


def test_webhook_secret_and_opaque_callback() -> None:
    assert verify_webhook_secret("same-secret", "same-secret") is True
    assert verify_webhook_secret("wrong", "same-secret") is False

    token = "AbCdEfGhIjKlMnOpQrStUvWx"
    data = access_callback_data(token)
    assert parse_access_callback_data(data) == token
    assert len(data.encode("utf-8")) <= 64
    assert "APPROVE" not in data
    assert "REJECT" not in data


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telegram_gateway_timeout_seconds", 0),
        ("notification_worker_poll_seconds", 0),
        ("notification_worker_claim_ttl_seconds", 9),
        ("notification_worker_batch_size", 0),
        ("notification_worker_max_attempts", 0),
    ],
)
def test_invalid_delivery_settings_are_rejected(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"database_url": DATABASE_URL, field: value})
