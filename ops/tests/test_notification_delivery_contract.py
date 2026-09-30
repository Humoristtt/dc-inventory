#!/usr/bin/env python3
"""Transactional delivery and bounded Telegram Gateway contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

operations = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
operations_lower = operations.lower()

service = (
    ROOT / "backend/app/modules/notifications/service.py"
).read_text(encoding="utf-8")

worker = (
    ROOT / "backend/app/modules/notifications/worker.py"
).read_text(encoding="utf-8")

gateway = (
    ROOT / "cloudflare/telegram-gateway/worker.mjs"
).read_text(encoding="utf-8")

assert "at-least-once" in operations_lower
assert any(
    "telegram" in paragraph.lower()
    and "at-least-once" in paragraph.lower()
    and "exactly-once" in paragraph.lower()
    and "потере ответа внешнего провайдера" in paragraph.lower()
    for paragraph in operations.split("\n\n")
)
assert "Dedupe key предотвращает дублирование outbox intent" in operations

assert "dedupe_key" in service
assert "on_conflict_do_nothing" in service
assert "claim_notification_batch" in worker
assert "mark_notification_sent" in worker

assert "MAX_BODY_BYTES = 64 * 1024" in gateway
assert "readBodyLimited" in gateway
assert "request.text()" not in gateway
assert "totalBytes > maxBytes" in gateway

print("NOTIFICATION_DELIVERY_CONTRACT=PASS")
print("GATEWAY_BOUNDED_BODY_CONTRACT=PASS")
