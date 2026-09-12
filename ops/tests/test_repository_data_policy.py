#!/usr/bin/env python3
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def require(path: str, value: str) -> None:
    text = (ROOT / path).read_text()
    if value not in text:
        raise RuntimeError(
            f"{path}: missing repository data policy assertion {value!r}"
        )


tracked = tracked_files()

for name in tracked:
    if name == ".env.example":
        continue

    base = Path(name).name

    if base == ".env" or base.startswith(".env."):
        raise RuntimeError(
            f"tracked environment file is forbidden: {name}"
        )

require(
    "README.md",
    "private/runtime-only production identifiers",
)
require(
    "README.md",
    "Публичные service identifiers",
)
require(
    "docs/OPERATIONS.md",
    "REPOSITORY_VISIBILITY_CURRENT=public",
)
require(
    "docs/OPERATIONS.md",
    "private/runtime-only identifiers",
)
require(
    "docs/OPERATIONS.md",
    "Public service identifiers",
)
require(
    "docs/OPERATIONS.md",
    "https://app.spik-inventory.ru",
)
require(
    "docs/DEPLOYMENT.md",
    "https://app.spik-inventory.ru",
)

env_example = (ROOT / ".env.example").read_text()

placeholder_keys = (
    "POSTGRES_PASSWORD",
    "POSTGRES_RUNTIME_PASSWORD",
    "POSTGRES_WORKER_PASSWORD",
    "POSTGRES_MAINTENANCE_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "TELEGRAM_GATEWAY_SECRET",
)

for key in placeholder_keys:
    match = re.search(
        rf"^{re.escape(key)}=(.+)$",
        env_example,
        flags=re.MULTILINE,
    )

    if match is None:
        raise RuntimeError(
            f".env.example: missing {key}"
        )

    if "replace-with-" not in match.group(1):
        raise RuntimeError(
            f".env.example: {key} must remain an obvious placeholder"
        )

if "ADMIN_TELEGRAM_USER_ID=123456789" not in env_example:
    raise RuntimeError(
        ".env.example: recovery Telegram ID must remain a placeholder"
    )

if "NOTIFICATION_TELEGRAM_USER_ID=987654321" not in env_example:
    raise RuntimeError(
        ".env.example: notification Telegram ID must remain a placeholder"
    )

bot_token_pattern = re.compile(
    r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"
)

private_key_markers = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)

for name in tracked:
    path = ROOT / name

    try:
        content = path.read_text()
    except (UnicodeDecodeError, OSError):
        continue

    if bot_token_pattern.search(content):
        raise RuntimeError(
            f"possible real Telegram bot token in tracked file: {name}"
        )

    for marker in private_key_markers:
        if marker in content:
            raise RuntimeError(
                f"private key material in tracked file: {name}"
            )

print("REPOSITORY_DATA_POLICY=PASS")
