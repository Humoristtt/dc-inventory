from __future__ import annotations

import uuid
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.modules.notifications import worker
from app.modules.notifications.gateway import TelegramGatewayClient
from app.modules.notifications.service import ClaimedNotification

DATABASE_URL = (
    "postgresql+asyncpg://dc_inventory:test@postgres:5432/"
    "dc_inventory"
)


class FakeBegin:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakeSession:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None

    def begin(self) -> FakeBegin:
        return FakeBegin()


class FakeGatewayClient:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def send(
        self,
        method: str,
        payload: dict[str, object],
    ) -> object:
        self.events.append(
            f"send:{payload['sequence']}"
        )
        return None


def make_claim(sequence: int) -> ClaimedNotification:
    return ClaimedNotification(
        id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        method="sendMessage",
        payload={"sequence": sequence},
        dedupe_key=f"test:{sequence}",
        attempts=1,
    )


def test_default_notification_worker_lease_is_safe() -> None:
    settings = Settings(database_url=DATABASE_URL)

    worker.validate_notification_worker_lease(settings)


def test_notification_worker_rejects_short_single_delivery_lease() -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        telegram_gateway_timeout_seconds=30,
        notification_worker_claim_ttl_seconds=60,
    )

    with pytest.raises(
        RuntimeError,
        match="NOTIFICATION_WORKER_CLAIM_TTL_SECONDS",
    ):
        worker.validate_notification_worker_lease(settings)


@pytest.mark.asyncio
async def test_worker_claims_each_notification_just_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    claims = [make_claim(1), make_claim(2)]

    async def fake_claim_notification_batch(
        db: object,
        *,
        batch_size: int,
        claim_ttl_seconds: int,
        max_attempts: int,
    ) -> list[ClaimedNotification]:
        assert batch_size == 1
        assert claim_ttl_seconds == 60
        assert max_attempts == 8

        if claims:
            claim = claims.pop(0)
            events.append(
                f"claim:{claim.payload['sequence']}"
            )
            return [claim]

        events.append("claim:empty")
        return []

    async def fake_finalize_success(
        engine: object,
        claim: ClaimedNotification,
    ) -> None:
        events.append(
            f"finalize:{claim.payload['sequence']}"
        )

    monkeypatch.setattr(
        worker,
        "AsyncSession",
        FakeSession,
    )
    monkeypatch.setattr(
        worker,
        "claim_notification_batch",
        fake_claim_notification_batch,
    )
    monkeypatch.setattr(
        worker,
        "_finalize_success",
        fake_finalize_success,
    )

    settings = Settings(
        database_url=DATABASE_URL,
        notification_worker_batch_size=3,
    )

    processed = await worker.run_worker_once(
        cast(AsyncEngine, object()),
        cast(
            TelegramGatewayClient,
            FakeGatewayClient(events),
        ),
        settings,
    )

    assert processed == 2
    assert events == [
        "claim:1",
        "send:1",
        "finalize:1",
        "claim:2",
        "send:2",
        "finalize:2",
        "claim:empty",
    ]



def test_start_welcome_context_is_strict() -> None:
    valid = ClaimedNotification(
        id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        method="sendMessage",
        payload={},
        dedupe_key="telegram-start-welcome:123:456",
        attempts=1,
    )
    malformed = ClaimedNotification(
        id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        method="sendMessage",
        payload={},
        dedupe_key="telegram-start-welcome:not-an-id:456",
        attempts=1,
    )
    unrelated = ClaimedNotification(
        id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        method="sendMessage",
        payload={},
        dedupe_key="something-else",
        attempts=1,
    )

    assert worker._start_welcome_context(valid) == (123, 456)
    assert worker._start_welcome_context(malformed) is None
    assert worker._start_welcome_context(unrelated) is None


def test_telegram_message_id_rejects_invalid_shapes() -> None:
    assert worker._telegram_message_id({"message_id": 42}) == 42
    assert worker._telegram_message_id({"message_id": True}) is None
    assert worker._telegram_message_id({"message_id": 0}) is None
    assert worker._telegram_message_id({}) is None
    assert worker._telegram_message_id(None) is None

@pytest.mark.asyncio
async def test_current_start_welcome_finalizes_state_without_followup_reaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    claim = ClaimedNotification(
        id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        method="sendMessage",
        payload={"chat_id": 456, "text": "welcome"},
        dedupe_key="telegram-start-welcome:123:456",
        attempts=1,
    )
    claims = [claim]

    class WelcomeGateway:
        async def send(
            self,
            method: str,
            payload: dict[str, object],
        ) -> object:
            events.append(f"send:{method}")
            if method == "sendMessage":
                return {"message_id": 321}
            return True

    async def fake_claim_notification_batch(
        db: object,
        *,
        batch_size: int,
        claim_ttl_seconds: int,
        max_attempts: int,
    ) -> list[ClaimedNotification]:
        del db, batch_size, claim_ttl_seconds, max_attempts
        if claims:
            events.append("claim")
            return [claims.pop(0)]
        events.append("claim:empty")
        return []

    async def fake_is_current_start(
        engine: object,
        *,
        chat_id: int,
        update_id: int,
    ) -> bool:
        del engine
        assert (chat_id, update_id) == (456, 123)
        return True

    async def fake_finalize_start_welcome_success(
        engine: object,
        claimed: ClaimedNotification,
        *,
        chat_id: int,
        update_id: int,
        message_id: int,
    ) -> bool:
        del engine
        assert claimed is claim
        assert (chat_id, update_id, message_id) == (456, 123, 321)
        events.append("finalize:start")
        return True

    monkeypatch.setattr(worker, "AsyncSession", FakeSession)
    monkeypatch.setattr(
        worker,
        "claim_notification_batch",
        fake_claim_notification_batch,
    )
    monkeypatch.setattr(
        worker,
        "_is_current_start",
        fake_is_current_start,
    )
    monkeypatch.setattr(
        worker,
        "_finalize_start_welcome_success",
        fake_finalize_start_welcome_success,
    )

    settings = Settings(
        database_url=DATABASE_URL,
        notification_worker_batch_size=2,
    )

    processed = await worker.run_worker_once(
        cast(AsyncEngine, object()),
        cast(TelegramGatewayClient, WelcomeGateway()),
        settings,
    )

    assert processed == 1
    assert events == [
        "claim",
        "send:sendMessage",
        "finalize:start",
        "claim:empty",
    ]


@pytest.mark.asyncio
async def test_stale_start_welcome_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    claim = ClaimedNotification(
        id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        method="sendMessage",
        payload={"chat_id": 456, "text": "stale"},
        dedupe_key="telegram-start-welcome:122:456",
        attempts=1,
    )
    claims = [claim]

    class NoSendGateway:
        async def send(
            self,
            method: str,
            payload: dict[str, object],
        ) -> object:
            del method, payload
            raise AssertionError("stale welcome must not reach Telegram")

    async def fake_claim_notification_batch(
        db: object,
        *,
        batch_size: int,
        claim_ttl_seconds: int,
        max_attempts: int,
    ) -> list[ClaimedNotification]:
        del db, batch_size, claim_ttl_seconds, max_attempts
        if claims:
            events.append("claim")
            return [claims.pop(0)]
        events.append("claim:empty")
        return []

    async def fake_is_current_start(
        engine: object,
        *,
        chat_id: int,
        update_id: int,
    ) -> bool:
        del engine
        assert (chat_id, update_id) == (456, 122)
        return False

    async def fake_finalize_success(
        engine: object,
        claimed: ClaimedNotification,
    ) -> None:
        del engine
        assert claimed is claim
        events.append("finalize:stale")

    monkeypatch.setattr(worker, "AsyncSession", FakeSession)
    monkeypatch.setattr(
        worker,
        "claim_notification_batch",
        fake_claim_notification_batch,
    )
    monkeypatch.setattr(
        worker,
        "_is_current_start",
        fake_is_current_start,
    )
    monkeypatch.setattr(
        worker,
        "_finalize_success",
        fake_finalize_success,
    )

    settings = Settings(
        database_url=DATABASE_URL,
        notification_worker_batch_size=2,
    )

    processed = await worker.run_worker_once(
        cast(AsyncEngine, object()),
        cast(TelegramGatewayClient, NoSendGateway()),
        settings,
    )

    assert processed == 1
    assert events == [
        "claim",
        "finalize:stale",
        "claim:empty",
    ]
