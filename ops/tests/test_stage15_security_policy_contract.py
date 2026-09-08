#!/usr/bin/env python3

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def read(name: str) -> str:
    return (ROOT / name).read_text()


operations = read("docs/OPERATIONS.md")
architecture = read("docs/ARCHITECTURE.md")
tracker = read("docs/STAGE15_AUDIT_REMEDIATION.md")

for value in (
    "AUD17_HOST_AUDIT=READ_ONLY_RECORDED",
    "UFW_STATUS=INACTIVE_RECORDED_FINDING",
    "SSH_ROOT_LOGIN=DISABLED",
    "SSH_PASSWORD_AUTH=DISABLED",
    "APP_HOST_BIND=127.0.0.1:8080",
    "POSTGRES_HOST_PORT=NONE",
    "REPOSITORY_VISIBILITY_CURRENT=public",
    "REPOSITORY_DATA_POLICY=NO_REAL_INVENTORY_DATA_IN_GIT",
):
    assert value in operations, value

for stale_value in (
    "REPOSITORY_VISIBILITY_BEFORE_REAL_INVENTORY=REASSESS_REQUIRED",
    "AUD19_DECISION=REASSESS_BEFORE_REAL_INVENTORY",
):
    assert stale_value not in operations, stale_value

assert (
    "TELEGRAM_DELIVERY_GUARANTEE="
    "AT_LEAST_ONCE_NOT_EXACTLY_ONCE"
) in architecture

assert re.search(
    r"Duplicate\s+delivery window",
    architecture,
)
assert "exactly-once" in architecture
assert "может быть отправлена повторно" in architecture
assert "notification is not a unique ledger event" not in architecture

assert "- [x] AUD-04" in tracker
assert "- [x] AUD-05" in tracker
assert "BATCH_B=PASS" in tracker
assert "AUD17_HOST_AUDIT=READ_ONLY_RECORDED" in tracker
assert (
    "REPOSITORY_VISIBILITY_BEFORE_REAL_INVENTORY=REASSESS_REQUIRED"
    in tracker
)

assert "UFW_STATUS=ENABLED" not in operations
assert "TELEGRAM_DELIVERY_GUARANTEE=EXACTLY_ONCE" not in architecture

print("HOST_SECURITY_AUDIT_CONTRACT=PASS")
print("TELEGRAM_DELIVERY_SEMANTICS_CONTRACT=PASS")
print("REPOSITORY_VISIBILITY_POLICY_CONTRACT=PASS")
print("AUD17_19_POLICY_CONTRACT=PASS")
