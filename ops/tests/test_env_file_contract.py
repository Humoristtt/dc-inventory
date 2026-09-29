#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "ops/validate_env_file.py"
EXAMPLE = ROOT / ".env.example"


def run(
    path: Path,
    *,
    production: bool = False,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        "python3",
        str(VALIDATOR),
    ]
    if production:
        arguments.append("--production")
    arguments.append(str(path))

    return subprocess.run(
        arguments,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


valid = run(EXAMPLE)
assert valid.returncode == 0, valid.stderr
assert "ENV_FILE_KEYS=PASS" in valid.stdout

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    typo = root / "typo.env"
    typo.write_text(
        "DATABASE_URL=postgresql://example\n"
        "DATABASE_POOL_SZE=10\n"
    )

    result = run(typo)
    assert result.returncode == 1
    assert (
        "unknown environment key DATABASE_POOL_SZE"
        in result.stderr
    )

    duplicate = root / "duplicate.env"
    duplicate.write_text(
        "APP_ENV=test\n"
        "APP_ENV=production\n"
    )

    result = run(duplicate)
    assert result.returncode == 1
    assert "duplicate key APP_ENV" in result.stderr

    malformed = root / "malformed.env"
    malformed.write_text(
        "APP_ENV=test\n"
        "THIS IS NOT AN ASSIGNMENT\n"
    )

    result = run(malformed)
    assert result.returncode == 1
    assert "invalid env assignment" in result.stderr

    production_placeholder = root / "production-placeholder.env"
    production_placeholder.write_text(
        "APP_ENV=production\n"
        "POSTGRES_PASSWORD=replace-with-a-strong-owner-secret\n"
        "TELEGRAM_BOT_TOKEN=replace-with-bot-token\n"
    )

    result = run(production_placeholder, production=True)
    assert result.returncode == 1
    assert (
        "production value for POSTGRES_PASSWORD is still a placeholder"
        in result.stderr
    )
    assert (
        "production value for TELEGRAM_BOT_TOKEN is still a placeholder"
        in result.stderr
    )

    production_unsafe_password = root / "production-unsafe-password.env"
    production_unsafe_password.write_text(
        "APP_ENV=production\n"
        "POSTGRES_PASSWORD=owner:secret@unsafe\n"
        "POSTGRES_RUNTIME_PASSWORD=runtime:secret@unsafe\n"
        "POSTGRES_TELEGRAM_WORKER_PASSWORD=telegram:secret@unsafe\n"
        "POSTGRES_EMAIL_WORKER_PASSWORD=email:secret@unsafe\n"
        "POSTGRES_MAINTENANCE_PASSWORD=maintenance:secret@unsafe\n"
    )

    result = run(production_unsafe_password, production=True)
    assert result.returncode == 1
    for key in (
        "POSTGRES_PASSWORD",
        "POSTGRES_RUNTIME_PASSWORD",
        "POSTGRES_TELEGRAM_WORKER_PASSWORD",
        "POSTGRES_EMAIL_WORKER_PASSWORD",
        "POSTGRES_MAINTENANCE_PASSWORD",
    ):
        assert (
            f"production value for {key} must be URL-safe"
            in result.stderr
        )

    production_safe_password = root / "production-safe-password.env"
    production_safe_password.write_text(
        "APP_ENV=production\n"
        "POSTGRES_PASSWORD=owner_secret-123.~\n"
        "POSTGRES_RUNTIME_PASSWORD=runtime_secret-123.~\n"
        "POSTGRES_TELEGRAM_WORKER_PASSWORD=telegram_secret-123.~\n"
        "POSTGRES_EMAIL_WORKER_PASSWORD=email_secret-123.~\n"
        "POSTGRES_MAINTENANCE_PASSWORD=maintenance_secret-123.~\n"
    )

    result = run(production_safe_password, production=True)
    assert result.returncode == 0, result.stderr



example = EXAMPLE.read_text()
compose = (ROOT / "compose.yaml").read_text()

assert (
    "INGRESS_HOST_DIR=/var/lib/dc-inventory-ingress"
    in example
)

assert (
    "ACCESS_CALLBACK_TTL_SECONDS: "
    "${ACCESS_CALLBACK_TTL_SECONDS:-900}"
    in compose
)

assert not (
    ROOT / "compose.tunnel-socket.yaml"
).exists()

print("ENV_FILE_CONTRACT=PASS")
