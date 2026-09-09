import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.identity.enums import UserAccessStatus, UserRole
from tests.warehouse_helpers import actor, move, scenario

pytestmark = pytest.mark.asyncio

type ApiUsers = dict[str, tuple[uuid.UUID, dict[str, str]]]


async def api_context(
    db: AsyncSession,
    enabled: bool = True,
) -> tuple[FastAPI, ApiUsers]:
    settings = Settings(app_env="test", real_inventory_mutations_enabled=enabled)
    app = create_app(settings)
    connection = await db.connection()

    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as request_db:
            yield request_db

    app.dependency_overrides[get_db_session] = session
    users: ApiUsers = {}
    for name, role, access in [
        ("admin", UserRole.ADMIN, UserAccessStatus.APPROVED),
        ("user", UserRole.USER, UserAccessStatus.APPROVED),
        ("pending", UserRole.USER, UserAccessStatus.PENDING),
        ("blocked", UserRole.USER, UserAccessStatus.BLOCKED),
        ("rejected", UserRole.USER, UserAccessStatus.REJECTED),
    ]:
        user, token = await actor(db, role, access)
        users[name] = (
            user.id,
            {
                "Cookie": f"{settings.auth_cookie_name}={token}",
                "Origin": settings.telegram_web_app_url,
            },
        )
    return app, users


async def test_read_access_and_actor_scoped_journal(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    s = await scenario(db)
    app, users = await api_context(db)
    first = await move(db, (users["user"][0], *s[1:]), "RETURN", 16, destination=s[2])
    other = await move(db, s, "RECEIPT", 20, destination=s[2])
    # Set the time before INSERT (the journal itself cannot be edited).
    from unittest.mock import patch

    from app.modules.inventory import service

    class OldClock:
        @staticmethod
        def now(tz: tzinfo | None) -> datetime:
            return datetime.now(UTC) - timedelta(days=150)

    with patch.object(service, "datetime", OldClock):
        await move(db, (users["user"][0], *s[1:]), "RETURN", 1, destination=s[2])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in [
            "/api/inventory/stock",
            "/api/inventory/locations",
            "/api/inventory/movements",
            "/api/inventory/movement-actors",
            f"/api/inventory/items/{s[1]}/summary",
        ]:
            assert (await client.get(path)).status_code == 401
            for name in ("pending", "blocked", "rejected"):
                assert (await client.get(path, headers=users[name][1])).status_code == 403
        response = await client.get("/api/inventory/movements", headers=users["user"][1])
        assert response.status_code == 200, response.text
        assert [m["id"] for m in response.json()["items"]] == [str(first.record.movement.id)]
        response = await client.get("/api/inventory/movements?period=all", headers=users["user"][1])
        assert response.json()["total"] == 2
        assert (
            await client.get(
                f"/api/inventory/movements?actor_user_id={s[0]}", headers=users["user"][1]
            )
        ).status_code == 403
        assert (
            await client.get(
                f"/api/inventory/movements/{other.record.movement.id}", headers=users["user"][1]
            )
        ).status_code == 403
        response = await client.get(
            f"/api/inventory/movements?actor_user_id={s[0]}&category=optics&location_id={s[2]}",
            headers=users["admin"][1],
        )
        assert response.json()["total"] == 1
        summary = await client.get(f"/api/inventory/items/{s[1]}/summary", headers=users["user"][1])
        assert summary.json()["total_count"] == 37
        assert summary.json()["locations"][0]["quantity"] == 37
        assert (
            await client.get(
                "/api/inventory/movements?since=2026-01-01T00:00:00", headers=users["admin"][1]
            )
        ).status_code == 422


async def test_mutation_roles_idempotency_and_gate(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    s = await scenario(db)
    await move(db, s, "RECEIPT", 10, destination=s[2])
    app, users = await api_context(db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for kind in ("ISSUE", "RETURN"):
            payload = {
                "movement_type": kind,
                "client_request_id": uuid.uuid4().hex,
                "lines": [{"item_id": str(s[1]), "quantity": 2}],
                ("source_location_id" if kind == "ISSUE" else "destination_location_id"): str(s[2]),
            }
            response = await client.post(
                "/api/inventory/movements", headers=users["user"][1], json=payload
            )
            assert response.status_code == 201, response.text
            assert response.json()["actor_user_id"] == str(users["user"][0])
            replay = await client.post(
                "/api/inventory/movements", headers=users["user"][1], json=payload
            )
            assert replay.json()["id"] == response.json()["id"]
            for restricted in ("RECEIPT", "TRANSFER", "WRITE_OFF", "CORRECTION", "REVERSAL"):
                assert (
                    await client.post(
                        "/api/inventory/movements",
                        headers=users["user"][1],
                        json={**payload, "movement_type": restricted},
                    )
                ).status_code == 403
        reversal = f"/api/admin/inventory/movements/{response.json()['id']}/reversal"
        assert (
            await client.post(
                reversal, headers=users["user"][1], json={"client_request_id": "reverse"}
            )
        ).status_code == 403
        assert (
            await client.post(
                reversal, headers=users["admin"][1], json={"client_request_id": "reverse"}
            )
        ).status_code == 201
        payload = {"code": uuid.uuid4().hex, "name": "Test location", "location_type": "DATACENTER"}
        assert (
            await client.post(
                "/api/admin/inventory/locations", headers=users["user"][1], json=payload
            )
        ).status_code == 403
        app.state.settings.real_inventory_mutations_enabled = False
        assert (
            await client.post(
                "/api/admin/inventory/locations", headers=users["admin"][1], json=payload
            )
        ).status_code == 423
        assert (
            await client.post(
                reversal, headers=users["admin"][1], json={"client_request_id": "gate"}
            )
        ).status_code == 423
        assert (
            await client.post(
                "/api/inventory/movements",
                headers=users["user"][1],
                json={
                    "movement_type": "RETURN",
                    "destination_location_id": str(s[2]),
                    "client_request_id": "gate",
                    "lines": [{"item_id": str(s[1]), "quantity": 1}],
                },
            )
        ).status_code == 423


async def test_issue_enqueues_one_admin_notification_and_replay_does_not_duplicate(
    warehouse_db: AsyncSession,
) -> None:
    from sqlalchemy import func, select

    from app.modules.notifications.models import NotificationOutbox
    from app.modules.notifications.service import notification_dedupe_key

    db = warehouse_db
    s = await scenario(db)
    await move(db, s, "RECEIPT", 10, destination=s[2])

    app, users = await api_context(db)
    app.state.settings.admin_telegram_user_id = 700000001

    issue_payload = {
        "movement_type": "ISSUE",
        "source_location_id": str(s[2]),
        "client_request_id": "issue-notification-test",
        "lines": [{"item_id": str(s[1]), "quantity": 2}],
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/inventory/movements",
            headers=users["user"][1],
            json=issue_payload,
        )
        assert response.status_code == 201, response.text

        movement_id = response.json()["id"]
        issue_key = notification_dedupe_key(
            "inventory-issue",
            movement_id,
            "admin",
        )

        replay = await client.post(
            "/api/inventory/movements",
            headers=users["user"][1],
            json=issue_payload,
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == movement_id

        issue_count = await db.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key == issue_key)
        )
        assert issue_count == 1

        total_before_return = await db.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )

        row = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.dedupe_key == issue_key)
        )
        assert row is not None
        assert row.method == "sendMessage"
        assert row.payload["chat_id"] == 700000001
        message_text = row.payload["text"]
        assert isinstance(message_text, str)
        assert "Выдача оборудования" in message_text
        assert "Откуда:" in message_text
        assert "2 шт." in message_text

        return_payload = {
            "movement_type": "RETURN",
            "destination_location_id": str(s[2]),
            "client_request_id": "return-no-notification-test",
            "lines": [{"item_id": str(s[1]), "quantity": 1}],
        }

        response = await client.post(
            "/api/inventory/movements",
            headers=users["user"][1],
            json=return_payload,
        )
        assert response.status_code == 201, response.text

        issue_count = await db.scalar(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key == issue_key)
        )
        assert issue_count == 1

        total_after_return = await db.scalar(
            select(func.count()).select_from(NotificationOutbox)
        )
        assert total_after_return == total_before_return


async def test_movement_feed_uses_stable_journal_cursor(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    app, users = await api_context(db)

    first = await move(
        db,
        s,
        "RECEIPT",
        10,
        destination=s[2],
    )
    second = await move(
        db,
        s,
        "RECEIPT",
        20,
        destination=s[2],
    )
    user_movement = await move(
        db,
        (users["user"][0], *s[1:]),
        "RETURN",
        1,
        destination=s[2],
    )
    fourth = await move(
        db,
        s,
        "RECEIPT",
        30,
        destination=s[2],
    )

    expected = sorted(
        [
            first.record.movement,
            second.record.movement,
            fourth.record.movement,
        ],
        key=lambda movement: movement.journal_seq,
        reverse=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        page1 = await client.get(
            "/api/inventory/movements/feed"
            "?period=all&limit=2"
            f"&actor_user_id={s[0]}",
            headers=users["admin"][1],
        )

        assert page1.status_code == 200, page1.text

        body1 = page1.json()

        assert [
            row["journal_seq"]
            for row in body1["items"]
        ] == [
            movement.journal_seq
            for movement in expected[:2]
        ]

        cursor = body1["next_before_journal_seq"]

        assert cursor == expected[1].journal_seq

        page2 = await client.get(
            "/api/inventory/movements/feed"
            f"?period=all&limit=2"
            f"&actor_user_id={s[0]}"
            f"&before_journal_seq={cursor}",
            headers=users["admin"][1],
        )

        assert page2.status_code == 200, page2.text

        body2 = page2.json()

        assert [
            row["journal_seq"]
            for row in body2["items"]
        ] == [
            movement.journal_seq
            for movement in expected[2:]
        ]

        assert body2["next_before_journal_seq"] is None

        user_page = await client.get(
            "/api/inventory/movements/feed"
            "?period=all&limit=10",
            headers=users["user"][1],
        )

        assert user_page.status_code == 200
        assert [
            row["id"]
            for row in user_page.json()["items"]
        ] == [
            str(user_movement.record.movement.id)
        ]

        forbidden = await client.get(
            "/api/inventory/movements/feed"
            f"?period=all"
            f"&actor_user_id={s[0]}",
            headers=users["user"][1],
        )

        assert forbidden.status_code == 403


async def test_actor_names_use_latest_journal_snapshot(warehouse_db: AsyncSession) -> None:
    from unittest.mock import patch

    from app.modules.inventory import service

    db = warehouse_db
    s = await scenario(db)
    app, users = await api_context(db)
    for name in ("Zulu old", "Alpha latest"):
        with patch.object(service, "normalize_inline_text", return_value=name):
            await move(db, (users["user"][0], *s[1:]), "RETURN", 1, destination=s[2])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/inventory/movement-actors", headers=users["user"][1])
    assert response.json() == [{"id": str(users["user"][0]), "name": "Alpha latest"}]


async def test_feed_period_uses_supplied_snapshot(warehouse_db: AsyncSession) -> None:
    from unittest.mock import patch

    from app.modules.inventory import service

    db = warehouse_db
    s = await scenario(db)
    app, users = await api_context(db)
    anchor = datetime(2026, 9, 9, 12, tzinfo=UTC)

    class Clock:
        @staticmethod
        def now(tz: tzinfo | None) -> datetime:
            return anchor - timedelta(days=7) + timedelta(seconds=1)

    with patch.object(service, "datetime", Clock):
        record = await move(db, (users["user"][0], *s[1:]), "RETURN", 1, destination=s[2])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = "/api/inventory/movements/feed"
        response = await client.get(path, headers=users["user"][1], params={
            "period": "7d", "snapshot_at": anchor.isoformat(),
        })
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["items"]] == [str(record.record.movement.id)]
        later = await client.get(path, headers=users["user"][1], params={
            "period": "7d", "snapshot_at": (anchor + timedelta(seconds=2)).isoformat(),
        })
        assert later.json()["items"] == []
        invalid = await client.get(path, headers=users["user"][1], params={
            "snapshot_at": "2026-09-09T12:00:00",
        })
        assert invalid.status_code == 422
