from app.modules.notifications.service import (
    notification_dedupe_key,
    retry_delay_seconds,
)


def test_notification_dedupe_key_is_deterministic_and_bounded() -> None:
    first = notification_dedupe_key("access", 123, "admin")
    second = notification_dedupe_key("access", 123, "admin")
    assert first == second
    assert len(first) == 64


def test_retry_backoff_is_bounded() -> None:
    assert retry_delay_seconds(1) == 1
    assert retry_delay_seconds(2) == 2
    assert retry_delay_seconds(3) == 4
    assert retry_delay_seconds(20) == 256
