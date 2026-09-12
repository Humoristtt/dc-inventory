from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from urllib.parse import urljoin, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.notifications.service import enqueue_telegram_call, notification_dedupe_key
from app.modules.procurement.models import ProcurementRevisionLine


def procurement_deep_link(settings: Settings, request_id: uuid.UUID) -> str:
    base = settings.telegram_web_app_url.strip().rstrip("/") + "/"
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("invalid Telegram Web App URL")
    return urljoin(base, f"procurement/{request_id}")


def _line_title(line: ProcurementRevisionLine) -> str:
    snapshot = line.display_snapshot
    manufacturer = snapshot.get("manufacturer_name")
    name = snapshot.get("name")
    model = snapshot.get("model")
    parts = [value for value in (manufacturer, name, model) if isinstance(value, str) and value]
    return " ".join(parts) or "Позиция закупки"


def composition_summary(lines: Sequence[ProcurementRevisionLine]) -> str:
    visible = [f"• {_line_title(line)} — {line.quantity} шт." for line in lines[:5]]
    if len(lines) > 5:
        visible.append(f"• и ещё {len(lines) - 5} поз.")
    return "\n".join(visible)


async def telegram_user_ids_for_users(
    db: AsyncSession,
    user_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, int]:
    unique = set(user_ids)
    if not unique:
        return {}
    rows = (
        await db.execute(
            select(TelegramIdentity.user_id, TelegramIdentity.telegram_user_id)
            .join(User, User.id == TelegramIdentity.user_id)
            .where(
                TelegramIdentity.user_id.in_(unique),
                User.access_status == UserAccessStatus.APPROVED,
            )
        )
    ).all()
    return {user_id: telegram_user_id for user_id, telegram_user_id in rows}


async def technical_recipient_user_ids(db: AsyncSession) -> set[uuid.UUID]:
    return set(
        (
            await db.scalars(
                select(User.id).where(
                    User.access_status == UserAccessStatus.APPROVED,
                    User.role.in_([UserRole.SENIOR_ENGINEER, UserRole.ADMIN, UserRole.OWNER]),
                )
            )
        ).all()
    )


async def enqueue_procurement_notifications(
    db: AsyncSession,
    *,
    settings: Settings,
    request_id: uuid.UUID,
    request_number: str,
    event_id: uuid.UUID,
    action: str,
    lines: Sequence[ProcurementRevisionLine],
    recipient_user_ids: Iterable[uuid.UUID],
) -> None:
    recipients = await telegram_user_ids_for_users(db, recipient_user_ids)
    if not recipients:
        return
    text = (
        f"Закупка {request_number}\n{action}\n\n"
        f"{composition_summary(lines)}\n\n"
        f"Открыть: {procurement_deep_link(settings, request_id)}"
    )
    for user_id, telegram_user_id in recipients.items():
        await enqueue_telegram_call(
            db,
            method="sendMessage",
            payload={
                "chat_id": telegram_user_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            dedupe_key=notification_dedupe_key("procurement", event_id, user_id, "telegram"),
        )
