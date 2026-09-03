from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.telegram_bot import service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chat_type",
    [
        None,
        "group",
        "supergroup",
        "channel",
    ],
)
async def test_start_is_ignored_outside_private_chat(
    monkeypatch: pytest.MonkeyPatch,
    chat_type: str | None,
) -> None:
    enqueue = AsyncMock()
    monkeypatch.setattr(
        service,
        "enqueue_start_message",
        enqueue,
    )

    chat: dict[str, object] = {
        "id": -1001234567890,
    }
    if chat_type is not None:
        chat["type"] = chat_type

    db = cast(AsyncSession, object())
    settings = cast(Settings, object())

    await service.process_telegram_update(
        db,
        update_id=100,
        payload={
            "message": {
                "message_id": 77,
                "text": "/start",
                "chat": chat,
                "from": {
                    "id": 123456789,
                    "first_name": "Group user",
                },
            },
        },
        settings=settings,
    )

    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_is_enqueued_for_private_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock()
    monkeypatch.setattr(
        service,
        "enqueue_start_message",
        enqueue,
    )

    db = cast(AsyncSession, object())
    settings = cast(Settings, object())

    await service.process_telegram_update(
        db,
        update_id=101,
        payload={
            "message": {
                "message_id": 78,
                "text": "/start@SpikatelInventoryBot payload",
                "chat": {
                    "id": 123456789,
                    "type": "private",
                },
                "from": {
                    "id": 123456789,
                    "first_name": "Вячеслав",
                },
            },
        },
        settings=settings,
    )

    enqueue.assert_awaited_once_with(
        db,
        chat_id=123456789,
        command_message_id=78,
        first_name="Вячеслав",
        update_id=101,
        settings=settings,
    )
