from pathlib import Path

from app.core.worker_health import (
    heartbeat_age_seconds,
    heartbeat_is_fresh,
    write_heartbeat,
)


def test_worker_heartbeat_freshness(
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "heartbeat"

    write_heartbeat(
        heartbeat,
        now=1000.0,
    )

    assert heartbeat.stat().st_mtime == 1000.0

    assert (
        heartbeat_age_seconds(
            heartbeat,
            now=1005.0,
        )
        == 5
    )

    assert heartbeat_is_fresh(
        heartbeat,
        max_age_seconds=10,
        now=1005.0,
    )

    assert not heartbeat_is_fresh(
        heartbeat,
        max_age_seconds=10,
        now=1011.0,
    )


def test_missing_worker_heartbeat_is_unhealthy(
    tmp_path: Path,
) -> None:
    assert not heartbeat_is_fresh(
        tmp_path / "missing",
        max_age_seconds=60,
    )
