"""Read-only outbox status: python -m app.modules.notifications.status.

SENT includes intentionally superseded notifications; it is not a delivery receipt.
Pending includes retries and in-flight claims. No payloads or recipient IDs are emitted.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import create_engine
from app.modules.notifications.models import NotificationOutbox as Outbox


async def outbox_status(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int | None]:
    now = now or datetime.now(UTC)
    pending = Outbox.status == "PENDING"
    row = (await db.execute(select(
        func.count().filter(pending),
        func.count().filter(pending & (Outbox.attempts > 0)),
        func.count().filter(Outbox.status == "DEAD"),
        func.count().filter(pending & Outbox.claimed_at.is_not(None)),
        func.min(Outbox.created_at).filter(pending),
        func.max(Outbox.sent_at),
    ))).one()

    def age(value: datetime | None) -> int | None:
        return max(0, int((now - value).total_seconds())) if value is not None else None

    return {
        "pending_count": row[0], "retry_count": row[1], "dead_count": row[2],
        "claimed_count": row[3], "oldest_pending_age_seconds": age(row[4]),
        "last_sent_state_age_seconds": age(row[5]),
    }


async def run() -> None:
    engine = create_engine(application_name="dc-inventory-notification-status")
    try:
        async with AsyncSession(engine) as db:
            print(json.dumps(await outbox_status(db), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
