import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"


def test_telegram_auth_defaults_and_support_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_INIT_DATA_MAX_AGE_SECONDS",
        "ADMIN_TELEGRAM_USER_ID",
        "NOTIFICATION_TELEGRAM_USER_ID",
        "SUPPORT_TELEGRAM_USERNAME",
        "AUTH_SESSION_TTL_SECONDS",
        "AUTH_COOKIE_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(database_url=DATABASE_URL)

    assert settings.telegram_bot_token_value is None
    assert settings.telegram_init_data_max_age_seconds == 300
    assert settings.admin_telegram_user_id is None
    assert settings.notification_telegram_user_id is None
    assert settings.support_telegram_username == "Humoristttt"
    assert settings.support_telegram_url == "https://t.me/Humoristttt"
    assert settings.auth_session_ttl_seconds == 43_200
    assert settings.auth_cookie_name == "dc_inventory_session"


def test_empty_telegram_ids_from_compose_become_none() -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        admin_telegram_user_id="",
        notification_telegram_user_id="",
    )

    assert settings.admin_telegram_user_id is None
    assert settings.notification_telegram_user_id is None


def test_telegram_bot_token_is_exposed_only_through_explicit_secret_accessor() -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        telegram_bot_token="secret-bot-token",
    )

    assert settings.telegram_bot_token_value == "secret-bot-token"
    assert "secret-bot-token" not in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telegram_init_data_max_age_seconds", 29),
        ("auth_session_ttl_seconds", 299),
        ("admin_telegram_user_id", 0),
        ("notification_telegram_user_id", 0),
        ("support_telegram_username", "bad-name"),
        ("auth_cookie_name", "bad cookie"),
    ],
)
def test_invalid_auth_settings_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"database_url": DATABASE_URL, field: value})
