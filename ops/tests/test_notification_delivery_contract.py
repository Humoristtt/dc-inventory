#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

operations = (
    ROOT / "docs/OPERATIONS.md"
).read_text()

service = (
    ROOT
    / "backend/app/modules/notifications/service.py"
).read_text()

worker = (
    ROOT
    / "backend/app/modules/notifications/worker.py"
).read_text()

gateway = (
    ROOT
    / "cloudflare/telegram-gateway/worker.mjs"
).read_text()

assert "at-least-once" in operations
assert (
    "Exactly-once Telegram delivery не заявляется"
    in operations
)
assert (
    "duplicate enqueue"
    in operations
)

assert "dedupe_key" in service
assert "on_conflict_do_nothing" in service
assert "claim_notification_batch" in worker
assert "mark_notification_sent" in worker

assert "MAX_BODY_BYTES = 64 * 1024" in gateway
assert "readBodyLimited" in gateway
assert "request.text()" not in gateway
assert (
    "totalBytes > maxBytes"
    in gateway
)

print(
    "NOTIFICATION_DELIVERY_CONTRACT=PASS"
)
print(
    "GATEWAY_BOUNDED_BODY_CONTRACT=PASS"
)
