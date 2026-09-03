from __future__ import annotations

import hmac
import html
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import AccessRequest, TelegramIdentity, User
from app.modules.notifications.service import (
    enqueue_telegram_call,
    notification_dedupe_key,
)
from app.modules.telegram_bot.models import (
    START_WELCOME_DEDUPE_PREFIX,
    AccessDecisionCallback,
    TelegramChatState,
    TelegramUpdate,
)

CALLBACK_PREFIX = "access:"
_CALLBACK_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,48}$")


class TelegramDeliveryConfigurationError(RuntimeError):
    """Telegram delivery configuration is incomplete."""


class InvalidAccessCallbackError(ValueError):
    """Callback data is malformed or unknown."""


class TelegramAdminAuthorizationError(PermissionError):
    """Callback actor is not an approved administrator."""


@dataclass(frozen=True, slots=True)
class AccessDecisionResult:
    status: AccessRequestStatus
    changed: bool


def verify_webhook_secret(
    provided: str | None,
    configured: str | None,
) -> bool:
    if provided is None or configured is None:
        return False
    return hmac.compare_digest(
        provided.encode("utf-8"),
        configured.encode("utf-8"),
    )


def parse_access_callback_data(data: str) -> str:
    if not data.startswith(CALLBACK_PREFIX):
        raise InvalidAccessCallbackError("invalid callback prefix")
    token = data[len(CALLBACK_PREFIX) :]
    if _CALLBACK_TOKEN_PATTERN.fullmatch(token) is None:
        raise InvalidAccessCallbackError("invalid callback token")
    return token


def access_callback_data(token: str) -> str:
    data = f"{CALLBACK_PREFIX}{token}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError("callback_data exceeds Telegram limit")
    return data


async def register_telegram_update(
    db: AsyncSession,
    update_id: int,
) -> bool:
    statement = (
        pg_insert(TelegramUpdate)
        .values(update_id=update_id)
        .on_conflict_do_nothing(index_elements=[TelegramUpdate.update_id])
        .returning(TelegramUpdate.update_id)
    )
    return await db.scalar(statement) is not None


async def mark_telegram_update_processed(
    db: AsyncSession,
    update_id: int,
    *,
    now: datetime | None = None,
) -> None:
    await db.execute(
        update(TelegramUpdate)
        .where(TelegramUpdate.update_id == update_id)
        .values(processed_at=now or datetime.now(UTC))
    )


async def create_access_decision_callbacks(
    db: AsyncSession,
    access_request_id: uuid.UUID,
) -> tuple[AccessDecisionCallback, AccessDecisionCallback]:
    approve = AccessDecisionCallback(
        token=secrets.token_urlsafe(18),
        access_request_id=access_request_id,
        action="APPROVE",
    )
    reject = AccessDecisionCallback(
        token=secrets.token_urlsafe(18),
        access_request_id=access_request_id,
        action="REJECT",
    )
    db.add_all([approve, reject])
    await db.flush()
    return approve, reject


async def get_or_create_access_decision_callbacks(
    db: AsyncSession,
    access_request_id: uuid.UUID,
) -> tuple[
    AccessDecisionCallback,
    AccessDecisionCallback,
]:
    existing = list(
        (
            await db.scalars(
                select(AccessDecisionCallback)
                .where(
                    AccessDecisionCallback.access_request_id
                    == access_request_id
                )
                .order_by(
                    AccessDecisionCallback.action
                )
            )
        ).all()
    )

    if not existing:
        return await create_access_decision_callbacks(
            db,
            access_request_id,
        )

    by_action = {
        callback.action: callback
        for callback in existing
    }

    approve = by_action.get("APPROVE")
    reject = by_action.get("REJECT")

    if (
        len(existing) != 2
        or approve is None
        or reject is None
    ):
        raise RuntimeError(
            "access decision callback pair is incomplete"
        )

    return approve, reject


def _display_identity(identity: TelegramIdentity) -> str:
    username = f"@{identity.username}" if identity.username else "без username"
    full_name = " ".join(
        part for part in (identity.first_name, identity.last_name) if part
    )
    return (
        f"{full_name}\n"
        f"{username}\n"
        f"Telegram ID: {identity.telegram_user_id}"
    )


async def enqueue_access_request_admin_notification(
    db: AsyncSession,
    *,
    access_request: AccessRequest,
    identity: TelegramIdentity,
    settings: Settings,
) -> None:
    admin_id = settings.admin_telegram_user_id
    if admin_id is None:
        raise TelegramDeliveryConfigurationError(
            "ADMIN_TELEGRAM_USER_ID is not configured"
        )

    approve, reject = (
        await get_or_create_access_decision_callbacks(
            db,
            access_request.id,
        )
    )
    await enqueue_telegram_call(
        db,
        method="sendMessage",
        payload={
            "chat_id": admin_id,
            "text": (
                "🔐 Новый запрос доступа к Spik Inventory\n\n"
                f"{_display_identity(identity)}"
            ),
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Разрешить",
                            "callback_data": access_callback_data(approve.token),
                        },
                        {
                            "text": "❌ Отклонить",
                            "callback_data": access_callback_data(reject.token),
                        },
                    ]
                ]
            },
        },
        dedupe_key=notification_dedupe_key(
            "access-request",
            access_request.id,
            "admin",
        ),
        requeue_dead=True,
    )


_START_WELCOME_DELETE_WINDOW = timedelta(hours=48)
_START_WELCOME_SEND_DELAY = timedelta(milliseconds=150)
_START_WELCOME_EFFECT_ID = "5113957245121463396"


def _start_welcome_dedupe_key(update_id: int, chat_id: int) -> str:
    return f"{START_WELCOME_DEDUPE_PREFIX}{update_id}:{chat_id}"


def _start_welcome_text(first_name: str, settings: Settings) -> str:
    safe_name = html.escape(first_name.strip() or "коллега")
    safe_support = html.escape(settings.support_telegram_username)
    return (
        f"<b>Привет, {safe_name}! 👋</b>\n\n"
        "Добро пожаловать в <b>Spikatel Inventory</b> — внутреннюю "
        "систему учёта оборудования ЦОД.\n\n"
        "Здесь можно найти оборудование, проверить остатки, посмотреть, "
        "у кого оно находится, а также работать с выдачей, возвратом "
        "и историей движений.\n\n"
        "По вопросам доступа и работы сервиса — "
        f"<b>@{safe_support}</b>."
    )


async def _register_latest_start(
    db: AsyncSession,
    *,
    chat_id: int,
    update_id: int,
) -> tuple[int, int | None, datetime | None]:
    insert_statement = pg_insert(TelegramChatState).values(
        chat_id=chat_id,
        latest_start_update_id=update_id,
    )
    statement = (
        insert_statement.on_conflict_do_update(
            index_elements=[TelegramChatState.chat_id],
            set_={
                "latest_start_update_id": func.greatest(
                    TelegramChatState.latest_start_update_id,
                    insert_statement.excluded.latest_start_update_id,
                ),
                "updated_at": func.now(),
            },
        )
        .returning(
            TelegramChatState.latest_start_update_id,
            TelegramChatState.last_welcome_message_id,
            TelegramChatState.last_welcome_sent_at,
        )
    )
    row = (await db.execute(statement)).one()
    return row[0], row[1], row[2]


async def enqueue_start_message(
    db: AsyncSession,
    *,
    chat_id: int,
    command_message_id: int,
    first_name: str,
    update_id: int,
    settings: Settings,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(UTC)

    await enqueue_telegram_call(
        db,
        method="deleteMessage",
        payload={
            "chat_id": chat_id,
            "message_id": command_message_id,
        },
        dedupe_key=notification_dedupe_key(
            "telegram-update",
            update_id,
            "delete-start",
        ),
        available_at=current_time,
    )

    latest_update_id, previous_message_id, previous_sent_at = (
        await _register_latest_start(
            db,
            chat_id=chat_id,
            update_id=update_id,
        )
    )

    # Webhook deliveries can overlap. An older /start still gets its command
    # removed, but it must not enqueue another welcome after a newer update won.
    if latest_update_id != update_id:
        return

    if (
        previous_message_id is not None
        and previous_sent_at is not None
        and current_time - previous_sent_at < _START_WELCOME_DELETE_WINDOW
    ):
        await enqueue_telegram_call(
            db,
            method="deleteMessage",
            payload={
                "chat_id": chat_id,
                "message_id": previous_message_id,
            },
            dedupe_key=notification_dedupe_key(
                "telegram-start",
                chat_id,
                previous_message_id,
                "delete-previous",
            ),
            available_at=current_time,
        )

    await enqueue_telegram_call(
        db,
        method="sendMessage",
        payload={
            "chat_id": chat_id,
            "text": _start_welcome_text(first_name, settings),
            "parse_mode": "HTML",
            "message_effect_id": _START_WELCOME_EFFECT_ID,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "Открыть приложение",
                            "web_app": {"url": settings.telegram_web_app_url},
                        }
                    ]
                ]
            },
        },
        dedupe_key=_start_welcome_dedupe_key(update_id, chat_id),
        available_at=current_time + _START_WELCOME_SEND_DELAY,
    )


async def _load_approved_admin(
    db: AsyncSession,
    telegram_user_id: int,
) -> User:
    identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.telegram_user_id == telegram_user_id
        )
    )
    if identity is None:
        raise TelegramAdminAuthorizationError

    user = await db.scalar(
        select(User)
        .where(User.id == identity.user_id)
        .with_for_update()
    )
    if (
        user is None
        or user.role != UserRole.ADMIN
        or user.access_status != UserAccessStatus.APPROVED
    ):
        raise TelegramAdminAuthorizationError
    return user


async def _enqueue_callback_answer(
    db: AsyncSession,
    *,
    callback_query_id: str,
    text: str,
) -> None:
    await enqueue_telegram_call(
        db,
        method="answerCallbackQuery",
        payload={"callback_query_id": callback_query_id, "text": text},
        dedupe_key=notification_dedupe_key(
            "callback",
            callback_query_id,
            "answer",
        ),
    )


async def enqueue_rejected_callback_answer(
    db: AsyncSession,
    *,
    callback_query_id: str,
    text: str,
) -> None:
    await _enqueue_callback_answer(
        db,
        callback_query_id=callback_query_id,
        text=text,
    )


async def _enqueue_admin_buttons_clear(
    db: AsyncSession,
    *,
    callback_query_id: str,
    message_chat_id: int | None,
    message_id: int | None,
) -> None:
    if message_chat_id is None or message_id is None:
        return
    await enqueue_telegram_call(
        db,
        method="editMessageReplyMarkup",
        payload={
            "chat_id": message_chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []},
        },
        dedupe_key=notification_dedupe_key(
            "callback",
            callback_query_id,
            "clear-buttons",
        ),
    )


async def _enqueue_user_decision(
    db: AsyncSession,
    *,
    access_request_id: uuid.UUID,
    target_identity: TelegramIdentity,
    status: AccessRequestStatus,
    settings: Settings,
) -> None:
    if status == AccessRequestStatus.APPROVED:
        text = "✅ Доступ предоставлен."
        reply_markup: dict[str, object] = {
            "inline_keyboard": [
                [
                    {
                        "text": "Открыть приложение",
                        "web_app": {"url": settings.telegram_web_app_url},
                    }
                ]
            ]
        }
    else:
        text = (
            "❌ Запрос доступа отклонён.\n\n"
            f"По вопросам доступа: @{settings.support_telegram_username}"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": f"@{settings.support_telegram_username}",
                        "url": settings.support_telegram_url,
                    }
                ]
            ]
        }

    await enqueue_telegram_call(
        db,
        method="sendMessage",
        payload={
            "chat_id": target_identity.telegram_user_id,
            "text": text,
            "reply_markup": reply_markup,
        },
        dedupe_key=notification_dedupe_key(
            "access-request",
            access_request_id,
            "user-decision",
        ),
    )


async def apply_access_decision(
    db: AsyncSession,
    *,
    callback_data: str,
    callback_query_id: str,
    actor_telegram_user_id: int,
    message_chat_id: int | None,
    message_id: int | None,
    settings: Settings,
    now: datetime | None = None,
) -> AccessDecisionResult:
    current_time = now or datetime.now(UTC)
    admin = await _load_approved_admin(db, actor_telegram_user_id)
    token = parse_access_callback_data(callback_data)

    callback = await db.scalar(
        select(AccessDecisionCallback)
        .where(AccessDecisionCallback.token == token)
        .with_for_update()
    )
    if callback is None:
        raise InvalidAccessCallbackError("unknown callback")

    access_request = await db.scalar(
        select(AccessRequest)
        .where(AccessRequest.id == callback.access_request_id)
        .with_for_update()
    )
    if access_request is None:
        raise InvalidAccessCallbackError("access request no longer exists")

    target_user = await db.scalar(
        select(User)
        .where(User.id == access_request.user_id)
        .with_for_update()
    )
    if target_user is None:
        raise RuntimeError("access request user no longer exists")

    if (
        access_request.status == AccessRequestStatus.PENDING
        and target_user.access_status != UserAccessStatus.PENDING
    ):
        raise InvalidAccessCallbackError(
            "user access state is already terminal"
        )

    target_identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.user_id == target_user.id
        )
    )
    if target_identity is None:
        raise RuntimeError("access request Telegram identity is missing")

    changed = access_request.status == AccessRequestStatus.PENDING
    if changed:
        if callback.action == "APPROVE":
            access_request.status = AccessRequestStatus.APPROVED
            target_user.access_status = UserAccessStatus.APPROVED
            target_user.approved_at = current_time
            target_user.approved_by_user_id = admin.id
        else:
            access_request.status = AccessRequestStatus.REJECTED
            target_user.access_status = UserAccessStatus.REJECTED
            target_user.approved_at = None
            target_user.approved_by_user_id = None

        access_request.decided_at = current_time
        access_request.decided_by_user_id = admin.id
        access_request.decision_note = "Telegram inline callback"

        await _enqueue_user_decision(
            db,
            access_request_id=access_request.id,
            target_identity=target_identity,
            status=access_request.status,
            settings=settings,
        )

    await _enqueue_admin_buttons_clear(
        db,
        callback_query_id=callback_query_id,
        message_chat_id=message_chat_id,
        message_id=message_id,
    )

    label = (
        "Доступ разрешён"
        if access_request.status == AccessRequestStatus.APPROVED
        else "Запрос отклонён"
    )
    if not changed:
        label = f"Уже решено: {label.lower()}"

    await _enqueue_callback_answer(
        db,
        callback_query_id=callback_query_id,
        text=label,
    )
    await db.flush()

    return AccessDecisionResult(
        status=access_request.status,
        changed=changed,
    )


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


async def process_telegram_update(
    db: AsyncSession,
    *,
    update_id: int,
    payload: dict[str, object],
    settings: Settings,
) -> None:
    message = payload.get("message")
    if isinstance(message, dict):
        text = message.get("text")
        chat = message.get("chat")
        if (
            isinstance(text, str)
            and text.split(maxsplit=1)[0].split("@", 1)[0] == "/start"
            and isinstance(chat, dict)
        ):
            chat_id = _integer(chat.get("id"))
            command_message_id = _integer(message.get("message_id"))
            sender = message.get("from")
            first_name = ""
            if isinstance(sender, dict):
                raw_first_name = sender.get("first_name")
                if isinstance(raw_first_name, str):
                    first_name = raw_first_name

            if chat_id is not None and command_message_id is not None:
                await enqueue_start_message(
                    db,
                    chat_id=chat_id,
                    command_message_id=command_message_id,
                    first_name=first_name,
                    update_id=update_id,
                    settings=settings,
                )
        return

    callback_query = payload.get("callback_query")
    if not isinstance(callback_query, dict):
        return

    callback_query_id = callback_query.get("id")
    actor = callback_query.get("from")
    callback_data = callback_query.get("data")
    if (
        not isinstance(callback_query_id, str)
        or not isinstance(actor, dict)
        or not isinstance(callback_data, str)
    ):
        return

    actor_id = _integer(actor.get("id"))
    if actor_id is None:
        return

    message_chat_id: int | None = None
    message_id: int | None = None
    callback_message = callback_query.get("message")
    if isinstance(callback_message, dict):
        message_id = _integer(callback_message.get("message_id"))
        chat = callback_message.get("chat")
        if isinstance(chat, dict):
            message_chat_id = _integer(chat.get("id"))

    try:
        await apply_access_decision(
            db,
            callback_data=callback_data,
            callback_query_id=callback_query_id,
            actor_telegram_user_id=actor_id,
            message_chat_id=message_chat_id,
            message_id=message_id,
            settings=settings,
        )
    except TelegramAdminAuthorizationError:
        await enqueue_rejected_callback_answer(
            db,
            callback_query_id=callback_query_id,
            text="Недостаточно прав",
        )
    except InvalidAccessCallbackError:
        await enqueue_rejected_callback_answer(
            db,
            callback_query_id=callback_query_id,
            text="Действие недоступно",
        )


def decode_update_json(raw: bytes) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid Telegram update JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Telegram update must be an object")
    return payload
