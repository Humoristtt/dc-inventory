from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.modules.notifications import worker
from app.modules.notifications.models import NotificationOutbox
from app.modules.notifications.service import notification_dedupe_key
from app.modules.telegram_bot.models import (
    START_WELCOME_DEDUPE_PREFIX,
    TelegramChatState,
)
from app.modules.telegram_bot.service import enqueue_start_message

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)

SETTINGS = Settings(database_url=DATABASE_URL)


async def _cleanup(
    db: AsyncSession,
    *,
    chat_id: int,
    dedupe_keys: list[str],
) -> None:
    if dedupe_keys:
        await db.execute(
            delete(NotificationOutbox).where(
                NotificationOutbox.dedupe_key.in_(dedupe_keys)
            )
        )
    await db.execute(
        delete(TelegramChatState).where(TelegramChatState.chat_id == chat_id)
    )
    await db.commit()


@pytest.mark.asyncio
async def test_start_refresh_personalizes_and_deletes_recent_previous() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    chat_id = 7_990_000_001
    update_id = 2_147_100_001
    command_message_id = 91
    previous_message_id = 77
    now = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)

    command_key = notification_dedupe_key(
        "telegram-update", update_id, "delete-start"
    )
    previous_key = notification_dedupe_key(
        "telegram-start",
        chat_id,
        previous_message_id,
        "delete-previous",
    )
    welcome_key = f"{START_WELCOME_DEDUPE_PREFIX}{update_id}:{chat_id}"
    keys = [command_key, previous_key, welcome_key]

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await _cleanup(db, chat_id=chat_id, dedupe_keys=keys)
            db.add(
                TelegramChatState(
                    chat_id=chat_id,
                    latest_start_update_id=update_id - 1,
                    last_welcome_message_id=previous_message_id,
                    last_welcome_sent_at=now - timedelta(hours=1),
                )
            )
            await db.commit()

            await enqueue_start_message(
                db,
                chat_id=chat_id,
                command_message_id=command_message_id,
                first_name="Вячеслав <Ops>",
                update_id=update_id,
                settings=SETTINGS,
                now=now,
            )
            await db.commit()

            rows = list(
                (
                    await db.scalars(
                        select(NotificationOutbox).where(
                            NotificationOutbox.dedupe_key.in_(keys)
                        )
                    )
                ).all()
            )
            assert len(rows) == 3
            by_key = {row.dedupe_key: row for row in rows}

            assert by_key[command_key].method == "deleteMessage"
            assert by_key[command_key].payload == {
                "chat_id": chat_id,
                "message_id": command_message_id,
            }

            assert by_key[previous_key].method == "deleteMessage"
            assert by_key[previous_key].payload == {
                "chat_id": chat_id,
                "message_id": previous_message_id,
            }

            welcome = by_key[welcome_key]
            assert welcome.method == "sendMessage"
            assert welcome.available_at > by_key[command_key].available_at
            assert welcome.payload["parse_mode"] == "HTML"
            assert welcome.payload["message_effect_id"] == "5113957245121463396"
            welcome_text = welcome.payload["text"]
            assert isinstance(welcome_text, str)
            assert (
                "<b>Привет, Вячеслав &lt;Ops&gt;! 👋</b>"
                in welcome_text
            )
            assert "<b>Spikatel Inventory</b>" in welcome_text
            assert "<b>@Humoristttt</b>" in welcome_text
            assert welcome.payload["reply_markup"] == {
                "inline_keyboard": [
                    [
                        {
                            "text": "Открыть приложение",
                            "web_app": {
                                "url": "https://app.spik-inventory.ru"
                            },
                        }
                    ]
                ]
            }

            state = await db.get(TelegramChatState, chat_id)
            assert state is not None
            assert state.latest_start_update_id == update_id
            assert state.last_welcome_message_id == previous_message_id

            await _cleanup(db, chat_id=chat_id, dedupe_keys=keys)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_start_refresh_keeps_previous_after_48_hour_window() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    chat_id = 7_990_000_002
    update_id = 2_147_100_002
    command_message_id = 92
    previous_message_id = 78
    now = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)

    command_key = notification_dedupe_key(
        "telegram-update", update_id, "delete-start"
    )
    previous_key = notification_dedupe_key(
        "telegram-start",
        chat_id,
        previous_message_id,
        "delete-previous",
    )
    welcome_key = f"{START_WELCOME_DEDUPE_PREFIX}{update_id}:{chat_id}"
    keys = [command_key, previous_key, welcome_key]

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await _cleanup(db, chat_id=chat_id, dedupe_keys=keys)
            db.add(
                TelegramChatState(
                    chat_id=chat_id,
                    latest_start_update_id=update_id - 1,
                    last_welcome_message_id=previous_message_id,
                    last_welcome_sent_at=now - timedelta(hours=49),
                )
            )
            await db.commit()

            await enqueue_start_message(
                db,
                chat_id=chat_id,
                command_message_id=command_message_id,
                first_name="Вячеслав",
                update_id=update_id,
                settings=SETTINGS,
                now=now,
            )
            await db.commit()

            previous_delete = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key == previous_key
                )
            )
            assert previous_delete is None

            command_delete = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key == command_key
                )
            )
            welcome = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key == welcome_key
                )
            )
            assert command_delete is not None
            assert welcome is not None

            await _cleanup(db, chat_id=chat_id, dedupe_keys=keys)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_latest_start_wins_worker_state_guard() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    chat_id = 7_990_000_003
    old_update_id = 2_147_100_003
    new_update_id = old_update_id + 1
    old_welcome_key = (
        f"{START_WELCOME_DEDUPE_PREFIX}{old_update_id}:{chat_id}"
    )
    new_welcome_key = (
        f"{START_WELCOME_DEDUPE_PREFIX}{new_update_id}:{chat_id}"
    )
    keys = [
        notification_dedupe_key(
            "telegram-update", old_update_id, "delete-start"
        ),
        notification_dedupe_key(
            "telegram-update", new_update_id, "delete-start"
        ),
        old_welcome_key,
        new_welcome_key,
    ]
    now = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            await _cleanup(db, chat_id=chat_id, dedupe_keys=keys)

            await enqueue_start_message(
                db,
                chat_id=chat_id,
                command_message_id=101,
                first_name="First",
                update_id=old_update_id,
                settings=SETTINGS,
                now=now,
            )
            await enqueue_start_message(
                db,
                chat_id=chat_id,
                command_message_id=102,
                first_name="Second",
                update_id=new_update_id,
                settings=SETTINGS,
                now=now,
            )
            await db.commit()

            state = await db.get(TelegramChatState, chat_id)
            assert state is not None
            assert state.latest_start_update_id == new_update_id

        assert (
            await worker._is_current_start(
                engine,
                chat_id=chat_id,
                update_id=old_update_id,
            )
            is False
        )
        assert (
            await worker._is_current_start(
                engine,
                chat_id=chat_id,
                update_id=new_update_id,
            )
            is True
        )

        assert (
            await worker._record_welcome_if_current(
                engine,
                chat_id=chat_id,
                update_id=old_update_id,
                message_id=301,
            )
            is False
        )
        assert (
            await worker._record_welcome_if_current(
                engine,
                chat_id=chat_id,
                update_id=new_update_id,
                message_id=302,
            )
            is True
        )

        async with AsyncSession(engine, expire_on_commit=False) as db:
            state = await db.get(TelegramChatState, chat_id)
            assert state is not None
            assert state.last_welcome_message_id == 302
            assert state.last_welcome_sent_at is not None
            await _cleanup(db, chat_id=chat_id, dedupe_keys=keys)
    finally:
        await engine.dispose()
