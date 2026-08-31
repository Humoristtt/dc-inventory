import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from app.modules.auth.telegram import (
    TelegramInitDataError,
    validate_telegram_init_data,
)

BOT_TOKEN = "123456789:test-token-for-unit-tests"
NOW = datetime(2026, 9, 1, 0, 30, tzinfo=UTC)


def _signed_init_data(
    *,
    user: dict[str, object] | None = None,
    auth_date: datetime = NOW,
    extra: dict[str, str] | None = None,
) -> str:
    fields = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            user
            or {
                "id": 42424242,
                "first_name": "Иван",
                "last_name": "Иванов",
                "username": "ivanov",
                "language_code": "ru",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    }
    if extra:
        fields.update(extra)

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()
    fields["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(fields)


def test_valid_telegram_init_data_is_accepted() -> None:
    validated = validate_telegram_init_data(
        _signed_init_data(),
        bot_token=BOT_TOKEN,
        max_age_seconds=300,
        now=NOW,
    )

    assert validated.user.id == 42424242
    assert validated.user.username == "ivanov"
    assert validated.user.first_name == "Иван"
    assert validated.auth_date == NOW
    assert validated.query_id == "AAHdF6IQAAAAAN0XohDhrOrc"


def test_tampered_telegram_user_is_rejected() -> None:
    init_data = _signed_init_data().replace("ivanov", "attacker", 1)

    with pytest.raises(TelegramInitDataError, match="signature"):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=300,
            now=NOW,
        )


def test_expired_telegram_init_data_is_rejected() -> None:
    init_data = _signed_init_data(auth_date=NOW - timedelta(seconds=301))

    with pytest.raises(TelegramInitDataError, match="expired"):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=300,
            now=NOW,
        )


def test_materially_future_auth_date_is_rejected() -> None:
    init_data = _signed_init_data(auth_date=NOW + timedelta(seconds=31))

    with pytest.raises(TelegramInitDataError, match="future"):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=300,
            now=NOW,
        )


def test_duplicate_init_data_field_is_rejected() -> None:
    init_data = _signed_init_data() + "&auth_date=1"

    with pytest.raises(TelegramInitDataError, match="duplicate"):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=300,
            now=NOW,
        )


def test_bot_identity_is_rejected() -> None:
    init_data = _signed_init_data(
        user={
            "id": 42424242,
            "first_name": "Service bot",
            "is_bot": True,
        }
    )

    with pytest.raises(TelegramInitDataError, match="bot identity"):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=300,
            now=NOW,
        )


def test_missing_user_is_rejected_after_signature_validation() -> None:
    fields = {
        "auth_date": str(int(NOW.timestamp())),
        "query_id": "query",
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    with pytest.raises(TelegramInitDataError, match="user is missing"):
        validate_telegram_init_data(
            urlencode(fields),
            bot_token=BOT_TOKEN,
            max_age_seconds=300,
            now=NOW,
        )
