from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

DEFAULT_HEARTBEAT_FILE = Path(
    "/tmp/dc-inventory-worker-heartbeat"
)


def _heartbeat_file() -> Path:
    return Path(
        os.environ.get(
            "WORKER_HEARTBEAT_FILE",
            str(DEFAULT_HEARTBEAT_FILE),
        )
    )


def _interval_seconds() -> float:
    return float(
        os.environ.get(
            "WORKER_HEARTBEAT_INTERVAL_SECONDS",
            "10",
        )
    )


def _max_age_seconds() -> float:
    return float(
        os.environ.get(
            "WORKER_HEARTBEAT_MAX_AGE_SECONDS",
            "60",
        )
    )


def write_heartbeat(
    path: Path,
    *,
    now: float | None = None,
) -> None:
    timestamp = time.time() if now is None else now
    path.write_text(f"{timestamp}\n")
    os.utime(path, (timestamp, timestamp))


def write_worker_heartbeat() -> None:
    write_heartbeat(_heartbeat_file())


def heartbeat_age_seconds(
    path: Path,
    *,
    now: float | None = None,
) -> float:
    timestamp = time.time() if now is None else now
    return max(0.0, timestamp - path.stat().st_mtime)


def heartbeat_is_fresh(
    path: Path,
    *,
    max_age_seconds: float,
    now: float | None = None,
) -> bool:
    try:
        age = heartbeat_age_seconds(
            path,
            now=now,
        )
    except FileNotFoundError:
        return False

    return age <= max_age_seconds


async def heartbeat_forever() -> None:
    path = _heartbeat_file()
    interval = _interval_seconds()

    if interval <= 0:
        raise RuntimeError(
            "WORKER_HEARTBEAT_INTERVAL_SECONDS must be positive"
        )

    while True:
        write_heartbeat(path)
        await asyncio.sleep(interval)


def main() -> None:
    path = _heartbeat_file()
    max_age = _max_age_seconds()

    if max_age <= 0:
        raise SystemExit(1)

    if not heartbeat_is_fresh(
        path,
        max_age_seconds=max_age,
    ):
        raise SystemExit(1)

    print("ok")


if __name__ == "__main__":
    main()
