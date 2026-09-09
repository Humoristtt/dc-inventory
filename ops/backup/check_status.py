#!/usr/bin/env python3
"""Read-only backup readiness. JSON stdout; exit 0 ready, 1 unhealthy, 2 usage."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return parsed


def check(state_dir: Path, max_age_seconds: int, now: datetime) -> dict[str, object]:
    try:
        success = json.loads((state_dir / "last-success.json").read_text())
        status = json.loads((state_dir / "status.json").read_text())
        if not isinstance(success, dict) or not isinstance(status, dict):
            raise ValueError("invalid state")
        if success.get("state") != "success" or success.get("schema_version") != 2:
            raise ValueError("unverified state")
        # Dump start is a conservative recovery-point bound; upload completion is not.
        started = timestamp(success.get("started_at_utc"))
        verified = timestamp(success.get("verified_at_utc"))
        if not started <= verified <= now:
            raise ValueError("invalid clock order")
        age = int((now - started).total_seconds())
        if status.get("state") == "failure":
            reason = "last_attempt_failed"
        elif status.get("state") != "success":
            raise ValueError("invalid latest status")
        elif age > max_age_seconds:
            reason = "stale_backup"
        else:
            reason = "ready"
        return {"ready": reason == "ready", "reason": reason, "recovery_point_age_seconds": age}
    except (OSError, ValueError, TypeError, OverflowError):
        return {"ready": False, "reason": "missing_or_invalid_state"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/dc-inventory-backup"))
    parser.add_argument("--max-age-seconds", type=int, default=26 * 3600)
    args = parser.parse_args()
    if args.max_age_seconds <= 0:
        parser.error("--max-age-seconds must be positive")
    result = check(args.state_dir, args.max_age_seconds, datetime.now(timezone.utc))
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
