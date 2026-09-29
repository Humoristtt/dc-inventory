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
URL_SAFE_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")
URL_INTERPOLATED_SECRET_KEYS = {
    "POSTGRES_PASSWORD",
    "POSTGRES_RUNTIME_PASSWORD",
    "POSTGRES_TELEGRAM_WORKER_PASSWORD",
    "POSTGRES_EMAIL_WORKER_PASSWORD",
    "POSTGRES_MAINTENANCE_PASSWORD",
}


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



def parse_env_values(
    path: Path,
) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
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
            continue

        key = match.group(1)
        if key in values:
            continue

        raw_value = line[match.end():].strip()
        if (
            len(raw_value) >= 2
            and raw_value[0] == raw_value[-1]
            and raw_value[0] in {"'", '"'}
        ):
            raw_value = raw_value[1:-1]

        values[key] = raw_value

    return values, errors


def validate_env_file(
    path: Path,
    *,
    production: bool = False,
) -> list[str]:
    allowed, reference_errors = parse_env_keys(
        REFERENCE_ENV
    )
    actual, actual_errors = parse_env_keys(path)
    values, value_errors = parse_env_values(path)

    errors = [
        *reference_errors,
        *actual_errors,
        *value_errors,
    ]

    for key in sorted(actual - allowed):
        errors.append(
            f"{path}: unknown environment key {key}"
        )

    if production:
        for key, value in sorted(values.items()):
            if "replace-with-" in value:
                errors.append(
                    f"{path}: production value for {key} is still a placeholder"
                )

        for key in sorted(URL_INTERPOLATED_SECRET_KEYS):
            value = values.get(key)
            if value is None:
                continue

            if not value:
                errors.append(
                    f"{path}: production value for {key} must not be empty"
                )
                continue

            if URL_SAFE_SECRET_PATTERN.fullmatch(value) is None:
                errors.append(
                    f"{path}: production value for {key} must be URL-safe "
                    "(RFC 3986 unreserved characters only)"
                )

    return errors


def main() -> int:
    args = sys.argv[1:]
    production = False

    if args[:1] == ["--production"]:
        production = True
        args = args[1:]

    if len(args) != 1:
        print(
            "usage: validate_env_file.py [--production] PATH",
            file=sys.stderr,
        )
        return 2

    path = Path(args[0])

    if not path.is_file():
        print(
            f"environment file not found: {path}",
            file=sys.stderr,
        )
        return 2

    errors = validate_env_file(
        path,
        production=production,
    )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    keys, _ = parse_env_keys(path)

    mode = "production" if production else "keys"
    print(
        f"ENV_FILE_{mode.upper()}=PASS "
        f"file={path} keys={len(keys)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
