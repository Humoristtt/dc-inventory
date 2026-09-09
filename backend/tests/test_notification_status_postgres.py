from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import NotificationOutbox
from app.modules.notifications.status import outbox_status


async def test_status_counts_retries_and_historical_dead_without_payloads(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    now = datetime.now(UTC)
    baseline = await outbox_status(db, now=now)
    for state, attempts in [("PENDING", 0), ("PENDING", 2), ("DEAD", 8), ("SENT", 1)]:
        db.add(NotificationOutbox(
            method="sendMessage", payload={"text": "must not be emitted"},
            dedupe_key=str(uuid4()), status=state, attempts=attempts,
            created_at=now - timedelta(seconds=120), available_at=now,
            sent_at=now - timedelta(seconds=10) if state == "SENT" else None,
        ))
    await db.flush()
    result = await outbox_status(db, now=now)
    assert result["pending_count"] == (baseline["pending_count"] or 0) + 2
    assert result["retry_count"] == (baseline["retry_count"] or 0) + 1
    assert result["dead_count"] == (baseline["dead_count"] or 0) + 1
    assert result["oldest_pending_age_seconds"] is not None
    assert result["last_sent_state_age_seconds"] is not None
    assert "must not be emitted" not in str(result)
