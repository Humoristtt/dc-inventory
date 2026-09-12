from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings

_CURSOR_VERSION = 1
_CURSOR_TTL_SECONDS = 3600
_CLOCK_SKEW_SECONDS = 60
_NONPRODUCTION_SECRET = (
    b"dc-inventory-nonproduction-movement-feed-cursor-v1"
)
_KEY_DOMAIN = b"dc-inventory/movement-feed-cursor/key/v1"
_SIGNATURE_DOMAIN = b"dc-inventory/movement-feed-cursor/token/v1\x00"


class MovementFeedCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MovementFeedCursorState:
    snapshot_at: datetime
    database_snapshot: str
    before_journal_seq: int | None


def _encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)

    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as error:
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        ) from error


def _scope_digest(scope: Mapping[str, object]) -> str:
    canonical = json.dumps(
        scope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _cursor_key(settings: Settings) -> bytes:
    configured = settings.telegram_webhook_secret_value

    if configured is None:
        if settings.app_env == "production":
            raise RuntimeError(
                "production movement feed cursor signing "
                "requires TELEGRAM_WEBHOOK_SECRET"
            )
        return _NONPRODUCTION_SECRET

    return hmac.new(
        configured.encode("utf-8"),
        _KEY_DOMAIN,
        hashlib.sha256,
    ).digest()


def encode_movement_feed_cursor(
    settings: Settings,
    *,
    snapshot_at: datetime,
    database_snapshot: str,
    before_journal_seq: int | None,
    scope: Mapping[str, object],
    now: datetime | None = None,
) -> str:
    if snapshot_at.tzinfo is None:
        raise ValueError("snapshot_at must be timezone-aware")

    if not database_snapshot or len(database_snapshot) > 12_000:
        raise ValueError("invalid PostgreSQL snapshot")

    if (
        before_journal_seq is not None
        and before_journal_seq <= 0
    ):
        raise ValueError("before_journal_seq must be positive")

    current = now or datetime.now(UTC)

    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    payload = {
        "v": _CURSOR_VERSION,
        "iat": int(current.timestamp()),
        "snapshot_at": snapshot_at.isoformat(),
        "database_snapshot": database_snapshot,
        "before": before_journal_seq,
        "scope": _scope_digest(scope),
    }

    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    signature = hmac.new(
        _cursor_key(settings),
        _SIGNATURE_DOMAIN + raw,
        hashlib.sha256,
    ).digest()

    return f"{_encode_base64(raw)}.{_encode_base64(signature)}"


def decode_movement_feed_cursor(
    settings: Settings,
    token: str,
    *,
    scope: Mapping[str, object],
    now: datetime | None = None,
) -> MovementFeedCursorState:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as error:
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        ) from error

    raw = _decode_base64(payload_part)
    supplied_signature = _decode_base64(signature_part)

    expected_signature = hmac.new(
        _cursor_key(settings),
        _SIGNATURE_DOMAIN + raw,
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(
        supplied_signature,
        expected_signature,
    ):
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        ) from error

    if not isinstance(payload, dict):
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    version = payload.get("v")
    issued_at = payload.get("iat")
    snapshot_raw = payload.get("snapshot_at")
    database_snapshot = payload.get("database_snapshot")
    before = payload.get("before")
    supplied_scope = payload.get("scope")

    if version != _CURSOR_VERSION:
        raise MovementFeedCursorError(
            "unsupported movement feed cursor"
        )

    if isinstance(issued_at, bool) or not isinstance(issued_at, int):
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    current = now or datetime.now(UTC)

    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    age = int(current.timestamp()) - issued_at

    if (
        age < -_CLOCK_SKEW_SECONDS
        or age > _CURSOR_TTL_SECONDS
    ):
        raise MovementFeedCursorError(
            "expired movement feed cursor"
        )

    if supplied_scope != _scope_digest(scope):
        raise MovementFeedCursorError(
            "movement feed cursor does not match request"
        )

    if not isinstance(snapshot_raw, str):
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    try:
        snapshot_at = datetime.fromisoformat(snapshot_raw)
    except ValueError as error:
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        ) from error

    if snapshot_at.tzinfo is None:
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    if (
        not isinstance(database_snapshot, str)
        or not database_snapshot
        or len(database_snapshot) > 12_000
    ):
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    if before is not None and (
        isinstance(before, bool)
        or not isinstance(before, int)
        or before <= 0
    ):
        raise MovementFeedCursorError(
            "invalid movement feed cursor"
        )

    return MovementFeedCursorState(
        snapshot_at=snapshot_at,
        database_snapshot=database_snapshot,
        before_journal_seq=before,
    )
