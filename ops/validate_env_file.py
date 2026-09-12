#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ENV = ROOT / ".env.example"
KEY_PATTERN = re.compile(
    r"^(?:export\s+)?([A-Z][A-Z0-9_]*)\s*="
)


def parse_env_keys(
    path: Path,
) -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    errors: list[str] = []

    for line_number, raw_line in enumerate(
        path.read_text().splitlines(),
        start=1,
    ):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        match = KEY_PATTERN.match(line)

        if match is None:
            errors.append(
                f"{path}:{line_number}: invalid env assignment"
            )
            continue

        key = match.group(1)

        if key in keys:
            errors.append(
                f"{path}:{line_number}: duplicate key {key}"
            )
            continue

        keys.add(key)

    return keys, errors


def validate_env_file(path: Path) -> list[str]:
    allowed, reference_errors = parse_env_keys(
        REFERENCE_ENV
    )
    actual, actual_errors = parse_env_keys(path)

    errors = [
        *reference_errors,
        *actual_errors,
    ]

    for key in sorted(actual - allowed):
        errors.append(
            f"{path}: unknown environment key {key}"
        )

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: validate_env_file.py PATH",
            file=sys.stderr,
        )
        return 2

    path = Path(sys.argv[1])

    if not path.is_file():
        print(
            f"environment file not found: {path}",
            file=sys.stderr,
        )
        return 2

    errors = validate_env_file(path)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    keys, _ = parse_env_keys(path)

    print(
        f"ENV_FILE_KEYS=PASS "
        f"file={path} keys={len(keys)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
