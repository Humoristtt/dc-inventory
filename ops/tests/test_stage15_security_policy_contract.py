#!/usr/bin/env python3
"""Контракты безопасности: текущие требования отдельно от истории Stage15."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def require_all(name: str, content: str, markers: tuple[str, ...]) -> None:
    missing = [marker for marker in markers if marker not in content]
    if missing:
        raise AssertionError(
            f"{name}: missing required assertions: {missing!r}"
        )


operations = read("docs/OPERATIONS.md")
architecture = read("docs/ARCHITECTURE.md")
tracker = read("docs/STAGE15_AUDIT_REMEDIATION.md")

# Исторические результаты остаются в историческом журнале.
# Они не доказывают фактическое состояние production сегодня.
require_all(
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    tracker,
    (
        "- [x] AUD-04",
        "- [x] AUD-05",
        "BATCH_B=PASS",
        "AUD17_HOST_AUDIT=READ_ONLY_RECORDED",
        "UFW_STATUS=INACTIVE_RECORDED_FINDING",
        "REPOSITORY_VISIBILITY_BEFORE_REAL_INVENTORY=REASSESS_REQUIRED",
        "AUD19_DECISION=REASSESS_BEFORE_REAL_INVENTORY",
    ),
)

# OPERATIONS описывает требования к будущей проверке, а не
# выдаёт старые AUD-маркеры за сегодняшние измерения.
require_all(
    "docs/OPERATIONS.md",
    operations,
    (
        "нужно измерить повторно перед выпуском",
        "UFW active",
        "PermitRootLogin no",
        "PasswordAuthentication no",
        "PostgreSQL, backend и web не имеют host-published application ports",
        "/var/lib/dc-inventory-ingress/ingress.sock",
        "telegram-webhook.spik-inventory.ru/api/telegram/webhook",
        "REPOSITORY_VISIBILITY_CURRENT=public",
        "private/runtime-only идентификаторов",
        "Public service identifiers",
        "CP-07",
    ),
)

for historical_marker in (
    "REPOSITORY_VISIBILITY_BEFORE_REAL_INVENTORY=REASSESS_REQUIRED",
    "AUD19_DECISION=REASSESS_BEFORE_REAL_INVENTORY",
):
    assert historical_marker not in operations, historical_marker

# Outbox не гарантирует exactly-once внешнюю доставку.
require_all(
    "docs/ARCHITECTURE.md",
    architecture,
    (
        "dedupe key",
        "at-least-once",
        "при потерянном подтверждении Gateway/Graph",
        "повторное внешнее сообщение",
        "Exactly-once для такой границы не заявляется",
    ),
)

assert "UFW_STATUS=ENABLED" not in operations
assert "TELEGRAM_DELIVERY_GUARANTEE=EXACTLY_ONCE" not in architecture
assert "notification is not a unique ledger event" not in architecture

print("HOST_SECURITY_AUDIT_CONTRACT=PASS")
print("TELEGRAM_DELIVERY_SEMANTICS_CONTRACT=PASS")
print("REPOSITORY_VISIBILITY_POLICY_CONTRACT=PASS")
print("AUD17_19_POLICY_CONTRACT=PASS")
