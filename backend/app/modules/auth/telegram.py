from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_INIT_DATA_LENGTH = 16_384
MAX_INIT_DATA_FIELDS = 100
MAX_FUTURE_SKEW_SECONDS = 30
_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class TelegramInitDataError(ValueError):
    """Telegram initData не прошёл проверку целостности или свежести."""


class TelegramWebAppUser(BaseModel):
    id: int = Field(gt=0, le=2**52)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=64)
    language_code: str | None = Field(default=None, max_length=35)
    is_bot: bool = False

    model_config = ConfigDict(extra="ignore")


@dataclass(frozen=True, slots=True)
class ValidatedTelegramInitData:
    user: TelegramWebAppUser
    auth_date: datetime
    query_id: str | None


def _parse_unique_fields(init_data: str) -> dict[str, str]:
    if not init_data or len(init_data) > MAX_INIT_DATA_LENGTH:
        raise TelegramInitDataError("invalid initData length")

    try:
        pairs = parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=MAX_INIT_DATA_FIELDS,
        )
    except ValueError as exc:
        raise TelegramInitDataError("malformed initData") from exc

    fields: dict[str, str] = {}
    for key, value in pairs:
        if not key or key in fields:
            raise TelegramInitDataError("duplicate or empty initData field")
        fields[key] = value

    return fields


def _expected_hash(fields: dict[str, str], bot_token: str) -> str:
    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
        if key != "hash"
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def validate_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> ValidatedTelegramInitData:
    if not bot_token:
        raise TelegramInitDataError("bot token is not configured")

    fields = _parse_unique_fields(init_data)
    provided_hash = fields.get("hash")
    if provided_hash is None or _HASH_PATTERN.fullmatch(provided_hash) is None:
        raise TelegramInitDataError("invalid initData hash")

    expected_hash = _expected_hash(fields, bot_token)
    if not hmac.compare_digest(expected_hash, provided_hash.lower()):
        raise TelegramInitDataError("invalid initData signature")

    auth_date_raw = fields.get("auth_date")
    if auth_date_raw is None:
        raise TelegramInitDataError("auth_date is missing")

    try:
        auth_timestamp = int(auth_date_raw)
        auth_date = datetime.fromtimestamp(auth_timestamp, tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise TelegramInitDataError("invalid auth_date") from exc

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    age_seconds = (current_time - auth_date).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        raise TelegramInitDataError("auth_date is in the future")
    if age_seconds > max_age_seconds:
        raise TelegramInitDataError("initData is expired")

    user_raw = fields.get("user")
    if user_raw is None:
        raise TelegramInitDataError("user is missing")

    try:
        user_payload = json.loads(user_raw)
        user = TelegramWebAppUser.model_validate(user_payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise TelegramInitDataError("invalid Telegram user") from exc

    if user.is_bot:
        raise TelegramInitDataError("bot identity is not allowed")

    return ValidatedTelegramInitData(
        user=user,
        auth_date=auth_date,
        query_id=fields.get("query_id"),
    )
