from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings

TECHNICAL_RETENTION_TARGETS = frozenset(
    {
        "auth_sessions",
        "telegram_updates",
        "notification_outbox",
        "access_decision_callbacks",
    }
)

TECHNICAL_RETENTION_ADVISORY_LOCK_KEY = 0x4443494E56524554

_AUTH_SESSIONS_DELETE = """
WITH candidates AS (
    SELECT id
    FROM auth_sessions
    WHERE
        expires_at < :cutoff
        OR (
            revoked_at IS NOT NULL
            AND revoked_at < :cutoff
        )
    ORDER BY
        LEAST(
            expires_at,
            COALESCE(revoked_at, expires_at)
        ),
        id
    LIMIT :batch_size
)
DELETE FROM auth_sessions AS target
USING candidates
WHERE target.id = candidates.id
RETURNING 1
"""

_TELEGRAM_UPDATES_DELETE = """
WITH candidates AS (
    SELECT update_id
    FROM telegram_updates
    WHERE
        processed_at IS NOT NULL
        AND processed_at < :cutoff
    ORDER BY processed_at, update_id
    LIMIT :batch_size
)
DELETE FROM telegram_updates AS target
USING candidates
WHERE target.update_id = candidates.update_id
RETURNING 1
"""

_NOTIFICATION_OUTBOX_DELETE = """
WITH candidates AS (
    SELECT id
    FROM notification_outbox
    WHERE
        status IN ('SENT', 'DEAD')
        AND updated_at < :cutoff
        AND claimed_at IS NULL
        AND claim_token IS NULL
    ORDER BY updated_at, id
    LIMIT :batch_size
)
DELETE FROM notification_outbox AS target
USING candidates
WHERE target.id = candidates.id
RETURNING 1
"""

_ACCESS_CALLBACKS_DELETE = """
WITH candidates AS (
    SELECT callback.token
    FROM access_decision_callbacks AS callback
    JOIN access_requests AS request
      ON request.id = callback.access_request_id
    WHERE
        request.status IN ('APPROVED', 'REJECTED')
        AND request.decided_at IS NOT NULL
        AND request.decided_at < :cutoff
    ORDER BY request.decided_at, callback.token
    LIMIT :batch_size
)
DELETE FROM access_decision_callbacks AS target
USING candidates
WHERE target.token = candidates.token
RETURNING 1
"""


@dataclass(frozen=True, slots=True)
class RetentionCounts:
    auth_sessions: int
    telegram_updates: int
    notification_outbox: int
    access_decision_callbacks: int

    @property
    def total(self) -> int:
        return (
            self.auth_sessions
            + self.telegram_updates
            + self.notification_outbox
            + self.access_decision_callbacks
        )


async def _delete_batch(
    db: AsyncSession,
    *,
    statement: str,
    cutoff: datetime,
    batch_size: int,
) -> int:
    result = await db.execute(
        text(statement),
        {
            "cutoff": cutoff,
            "batch_size": batch_size,
        },
    )
    return len(result.all())


async def run_technical_retention_once(
    db: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> RetentionCounts:
    lock_acquired = await db.scalar(
        text(
            "SELECT pg_try_advisory_xact_lock(:lock_key)"
        ),
        {
            "lock_key": (
                TECHNICAL_RETENTION_ADVISORY_LOCK_KEY
            )
        },
    )

    if lock_acquired is not True:
        return RetentionCounts(
            auth_sessions=0,
            telegram_updates=0,
            notification_outbox=0,
            access_decision_callbacks=0,
        )

    current_time = now or datetime.now(UTC)
    batch_size = settings.maintenance_retention_batch_size

    auth_sessions = await _delete_batch(
        db,
        statement=_AUTH_SESSIONS_DELETE,
        cutoff=current_time
        - timedelta(days=settings.auth_session_retention_days),
        batch_size=batch_size,
    )
    telegram_updates = await _delete_batch(
        db,
        statement=_TELEGRAM_UPDATES_DELETE,
        cutoff=current_time
        - timedelta(days=settings.telegram_update_retention_days),
        batch_size=batch_size,
    )
    notification_outbox = await _delete_batch(
        db,
        statement=_NOTIFICATION_OUTBOX_DELETE,
        cutoff=current_time
        - timedelta(
            days=settings.notification_outbox_retention_days
        ),
        batch_size=batch_size,
    )
    access_decision_callbacks = await _delete_batch(
        db,
        statement=_ACCESS_CALLBACKS_DELETE,
        cutoff=current_time
        - timedelta(days=settings.access_callback_retention_days),
        batch_size=batch_size,
    )

    return RetentionCounts(
        auth_sessions=auth_sessions,
        telegram_updates=telegram_updates,
        notification_outbox=notification_outbox,
        access_decision_callbacks=access_decision_callbacks,
    )
