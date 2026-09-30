#!/usr/bin/env python3
"""Current security-policy contract without historical audit dependencies."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def require_all(name: str, value: str, markers: tuple[str, ...]) -> None:
    missing = [marker for marker in markers if marker not in value]
    if missing:
        raise AssertionError(f"{name}: missing required assertions: {missing!r}")


security = read("docs/SECURITY.md")
operations = read("docs/OPERATIONS.md")
architecture = read("docs/ARCHITECTURE.md")
compose = read("compose.yaml")
gateway = read("cloudflare/telegram-gateway/worker.mjs")
config = read("backend/app/core/config.py")

require_all(
    "docs/SECURITY.md",
    security,
    (
        "Backend capabilities",
        "REAL_INVENTORY_MUTATIONS_ENABLED=false",
        "Database least privilege",
        "Supply chain",
        "at-least-once",
        "Репозиторий рассматривается как публичный",
    ),
)

require_all(
    "docs/OPERATIONS.md",
    operations,
    (
        "измерить повторно",
        "UFW active",
        "PermitRootLogin no",
        "PasswordAuthentication no",
        "/var/lib/dc-inventory-ingress/ingress.sock",
        "REPOSITORY_VISIBILITY_CURRENT=public",
    ),
)

require_all(
    "docs/ARCHITECTURE.md",
    architecture,
    (
        "PostgreSQL как вторая граница корректности",
        "transactional outbox",
        "at-least-once",
        "Runtime provenance",
    ),
)

for marker in (
    "cap_drop:",
    "no-new-privileges:true",
    "read_only: true",
    "pids_limit:",
):
    assert marker in compose, marker

assert "real_inventory_mutations_enabled: bool = False" in config
assert "email_delivery_enabled: bool = False" in config

assert "MAX_BODY_BYTES = 64 * 1024" in gateway
assert "ALLOWED_METHODS" in gateway
assert "request.text()" not in gateway
assert "https://api.telegram.org/" in gateway

for stale in (
    "AUD17_",
    "AUD19_",
    "BATCH_B=PASS",
    "Stage15",
    "CP-07",
):
    assert stale not in security, stale

print("SECURITY_POLICY_CONTRACT=PASS")
