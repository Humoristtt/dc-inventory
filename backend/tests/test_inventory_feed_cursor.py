from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.modules.inventory.feed_cursor import (
    MovementFeedCursorError,
    decode_movement_feed_cursor,
    encode_movement_feed_cursor,
)

NOW = datetime(2026, 9, 12, 7, 0, tzinfo=UTC)


def settings() -> Settings:
    return Settings(
        app_env="test",
        telegram_webhook_secret="cursor-test-secret",
    )


def scope() -> dict[str, object]:
    return {
        "requester_user_id": "user-1",
        "period": "30d",
        "limit": 30,
        "actor_user_id": None,
        "movement_type": None,
        "category": None,
        "long_range": False,
        "location_id": None,
    }


def test_cursor_round_trip_and_scope_binding() -> None:
    token = encode_movement_feed_cursor(
        settings(),
        snapshot_at=NOW,
        database_snapshot="100:200:150,170",
        before_journal_seq=42,
        scope=scope(),
        now=NOW,
    )

    state = decode_movement_feed_cursor(
        settings(),
        token,
        scope=scope(),
        now=NOW,
    )

    assert state.snapshot_at == NOW
    assert state.database_snapshot == "100:200:150,170"
    assert state.before_journal_seq == 42

    rebound = scope()
    rebound["period"] = "7d"

    with pytest.raises(
        MovementFeedCursorError,
        match="does not match request",
    ):
        decode_movement_feed_cursor(
            settings(),
            token,
            scope=rebound,
            now=NOW,
        )


def test_cursor_is_tamper_evident_and_expires() -> None:
    token = encode_movement_feed_cursor(
        settings(),
        snapshot_at=NOW,
        database_snapshot="100:200:",
        before_journal_seq=None,
        scope=scope(),
        now=NOW,
    )

    payload, signature = token.split(".", 1)
    replacement = "A" if signature[0] != "A" else "B"
    tampered = (
        f"{payload}.{replacement}{signature[1:]}"
    )

    with pytest.raises(
        MovementFeedCursorError,
        match="invalid movement feed cursor",
    ):
        decode_movement_feed_cursor(
            settings(),
            tampered,
            scope=scope(),
            now=NOW,
        )

    with pytest.raises(
        MovementFeedCursorError,
        match="expired movement feed cursor",
    ):
        decode_movement_feed_cursor(
            settings(),
            token,
            scope=scope(),
            now=NOW + timedelta(hours=2),
        )
