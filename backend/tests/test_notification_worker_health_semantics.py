from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.notifications import worker
from app.modules.notifications.gateway import TelegramGatewayError


class _StopLoop(Exception):
    pass


def test_safe_delivery_error_keeps_safe_gateway_reason() -> None:
    error = TelegramGatewayError("gateway returned HTTP 503")

    assert worker._safe_delivery_error(error) == "TelegramGatewayError: gateway returned HTTP 503"


def test_safe_delivery_error_hides_generic_exception_message() -> None:
    error = RuntimeError("do-not-persist-this-message")

    assert worker._safe_delivery_error(error) == "RuntimeError"


@pytest.mark.asyncio
async def test_failed_iteration_does_not_refresh_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeats: list[str] = []

    async def failing_iteration(
        *_args: Any,
        **_kwargs: Any,
    ) -> int:
        raise RuntimeError("database unavailable")

    def heartbeat() -> None:
        heartbeats.append("beat")

    async def stop_sleep(_seconds: float) -> None:
        raise _StopLoop

    fake_asyncio = SimpleNamespace(
        sleep=stop_sleep,
    )
    settings = SimpleNamespace(
        notification_worker_poll_seconds=1,
    )

    monkeypatch.setattr(
        worker,
        "run_worker_once",
        failing_iteration,
    )
    monkeypatch.setattr(
        worker,
        "write_worker_heartbeat",
        heartbeat,
    )
    monkeypatch.setattr(
        worker,
        "asyncio",
        fake_asyncio,
    )

    with pytest.raises(_StopLoop):
        await worker._run_worker_loop(
            cast(Any, object()),
            cast(Any, object()),
            cast(Any, settings),
        )

    assert heartbeats == []


@pytest.mark.asyncio
async def test_successful_iteration_refreshes_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeats: list[str] = []

    async def successful_iteration(
        *_args: Any,
        **_kwargs: Any,
    ) -> int:
        return 0

    def heartbeat() -> None:
        heartbeats.append("beat")

    async def stop_sleep(_seconds: float) -> None:
        raise _StopLoop

    fake_asyncio = SimpleNamespace(
        sleep=stop_sleep,
    )
    settings = SimpleNamespace(
        notification_worker_poll_seconds=1,
    )

    monkeypatch.setattr(
        worker,
        "run_worker_once",
        successful_iteration,
    )
    monkeypatch.setattr(
        worker,
        "write_worker_heartbeat",
        heartbeat,
    )
    monkeypatch.setattr(
        worker,
        "asyncio",
        fake_asyncio,
    )

    with pytest.raises(_StopLoop):
        await worker._run_worker_loop(
            cast(Any, object()),
            cast(Any, object()),
            cast(Any, settings),
        )

    assert heartbeats == ["beat"]
