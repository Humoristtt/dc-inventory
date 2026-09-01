from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import NotificationOutbox

ALLOWED_TELEGRAM_METHODS = frozenset(
    {
        "sendMessage",
        "editMessageText",
        "editMessageReplyMarkup",
        "answerCallbackQuery",
    }
)


class UnsupportedTelegramMethodError(ValueError):
    """Outbox не принимает произвольные Telegram Bot API methods."""


@dataclass(frozen=True, slots=True)
class ClaimedNotification:
    id: uuid.UUID
    claim_token: uuid.UUID
    method: str
    payload: dict[str, object]
    attempts: int


def notification_dedupe_key(*parts: object) -> str:
    value = "|".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def enqueue_telegram_call(
    db: AsyncSession,
    *,
    method: str,
    payload: dict[str, object],
    dedupe_key: str,
    available_at: datetime | None = None,
) -> None:
    if method not in ALLOWED_TELEGRAM_METHODS:
        raise UnsupportedTelegramMethodError(method)
    if not dedupe_key or len(dedupe_key) > 128:
        raise ValueError("invalid outbox dedupe key")

    values: dict[str, object] = {
        "method": method,
        "payload": payload,
        "dedupe_key": dedupe_key,
    }
    if available_at is not None:
        values["available_at"] = available_at

    statement = (
        pg_insert(NotificationOutbox)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[NotificationOutbox.dedupe_key])
    )
    await db.execute(statement)


async def claim_notification_batch(
    db: AsyncSession,
    *,
    batch_size: int,
    claim_ttl_seconds: int,
    max_attempts: int,
    now: datetime | None = None,
) -> list[ClaimedNotification]:
    current_time = now or datetime.now(UTC)
    stale_before = current_time - timedelta(seconds=claim_ttl_seconds)

    rows = list(
        (
            await db.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status == "PENDING",
                    NotificationOutbox.available_at <= current_time,
                    or_(
                        NotificationOutbox.attempts < max_attempts,
                        (
                            (NotificationOutbox.attempts >= max_attempts)
                            & NotificationOutbox.claimed_at.is_not(None)
                            & (NotificationOutbox.claimed_at < stale_before)
                        ),
                    ),
                    or_(
                        NotificationOutbox.claimed_at.is_(None),
                        NotificationOutbox.claimed_at < stale_before,
                    ),
                )
                .order_by(
                    NotificationOutbox.available_at.asc(),
                    NotificationOutbox.created_at.asc(),
                    NotificationOutbox.id.asc(),
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )

    claimed: list[ClaimedNotification] = []
    for row in rows:
        token = uuid.uuid4()
        was_stale_final_attempt = (
            row.attempts >= max_attempts
            and row.claimed_at is not None
            and row.claimed_at < stale_before
        )
        row.claimed_at = current_time
        row.claim_token = token
        if not was_stale_final_attempt:
            row.attempts += 1
        claimed.append(
            ClaimedNotification(
                id=row.id,
                claim_token=token,
                method=row.method,
                payload=row.payload,
                attempts=row.attempts,
            )
        )

    await db.flush()
    return claimed


async def mark_notification_sent(
    db: AsyncSession,
    claim: ClaimedNotification,
    *,
    now: datetime | None = None,
) -> bool:
    row = await db.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.id == claim.id,
            NotificationOutbox.claim_token == claim.claim_token,
            NotificationOutbox.status == "PENDING",
        )
        .with_for_update()
    )
    if row is None:
        return False

    row.status = "SENT"
    row.sent_at = now or datetime.now(UTC)
    row.claimed_at = None
    row.claim_token = None
    row.last_error = None
    await db.flush()
    return True


def retry_delay_seconds(attempts: int) -> int:
    exponent = max(0, min(attempts - 1, 8))
    return min(300, 1 << exponent)


async def mark_notification_failed(
    db: AsyncSession,
    claim: ClaimedNotification,
    *,
    error: str,
    max_attempts: int,
    now: datetime | None = None,
) -> bool:
    current_time = now or datetime.now(UTC)
    row = await db.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.id == claim.id,
            NotificationOutbox.claim_token == claim.claim_token,
            NotificationOutbox.status == "PENDING",
        )
        .with_for_update()
    )
    if row is None:
        return False

    row.claimed_at = None
    row.claim_token = None
    row.last_error = error[:1000]

    if row.attempts >= max_attempts:
        row.status = "DEAD"
    else:
        row.available_at = current_time + timedelta(
            seconds=retry_delay_seconds(row.attempts)
        )

    await db.flush()
    return True
