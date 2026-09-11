import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.inventory.api import _raise_integrity_conflict
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
        ("owner", UserRole.OWNER, UserAccessStatus.APPROVED),
        ("senior", UserRole.SENIOR_ENGINEER, UserAccessStatus.APPROVED),
        ("manager", UserRole.MANAGER, UserAccessStatus.APPROVED),
        ("user", UserRole.ENGINEER, UserAccessStatus.APPROVED),
        ("pending", UserRole.ENGINEER, UserAccessStatus.PENDING),
        ("blocked", UserRole.ENGINEER, UserAccessStatus.BLOCKED),
        ("rejected", UserRole.ENGINEER, UserAccessStatus.REJECTED),
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


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        (
            "custody is only valid for issue, return, or reversal",
            "custody_movement_type_invalid",
        ),
        (
            "user issue/return custody must match movement actor",
            "custody_actor_mismatch",
        ),
        (
            "admin issue/return must not carry custody",
            "custody_admin_invalid",
        ),
        (
            "correction of custody movement is forbidden",
            "custody_correction_forbidden",
        ),
        (
            "reversal original movement not found",
            "reversal_original_not_found",
        ),
        (
            "reversal custody must match original movement",
            "reversal_custody_mismatch",
        ),
        (
            "custody reversal requires issue or return original",
            "reversal_custody_original_invalid",
        ),
    ],
)
async def test_known_custody_trigger_violation_is_safe_conflict(
    message: str,
    expected_code: str,
) -> None:
    class TriggerViolation(Exception):
        sqlstate = "23514"

        def __init__(self, value: str) -> None:
            super().__init__(value)
            self.message = value

    error = IntegrityError(
        "INSERT INTO movements ...",
        {},
        TriggerViolation(message),
    )

    with pytest.raises(HTTPException) as caught:
        _raise_integrity_conflict(error)

    assert caught.value.status_code == 409

    detail = cast(dict[str, str], caught.value.detail)

    assert detail == {
        "code": expected_code,
        "message": (
            "inventory custody constraint rejected the operation"
        ),
    }

    # Raw PostgreSQL trigger text must not leak through the API response.
    assert message not in str(detail)


async def test_unknown_check_violation_is_not_masked() -> None:
    class UnknownViolation(Exception):
        sqlstate = "23514"
        message = "some unrelated database check failed"

    error = IntegrityError(
        "INSERT INTO unrelated_table ...",
        {},
        UnknownViolation(),
    )

    with pytest.raises(IntegrityError) as caught:
        _raise_integrity_conflict(error)

    assert caught.value is error


async def test_read_access_and_actor_scoped_journal(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    s = await scenario(db)
    app, users = await api_context(db)
    other = await move(db, s, "RECEIPT", 20, destination=s[2])
    first = await move(
        db,
        (users["user"][0], *s[1:]),
        "ISSUE",
        1,
        source=s[2],
        custody_user_id=users["user"][0],
    )
    # Inject the timestamp before INSERT; the journal itself cannot be edited.
    from unittest.mock import patch

    from app.modules.inventory import service

    old_timestamp = datetime.now(UTC) - timedelta(days=150)

    async def old_movement_timestamp(
        _db: AsyncSession,
    ) -> datetime:
        return old_timestamp

    with patch.object(
        service,
        "_movement_timestamp",
        old_movement_timestamp,
    ):
        await move(
            db,
            (users["user"][0], *s[1:]),
            "RETURN",
            1,
            destination=s[2],
            custody_user_id=users["user"][0],
        )
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
        assert summary.json()["total_count"] == 20
        assert summary.json()["locations"][0]["quantity"] == 20
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
            assert response.json()["custody_user_id"] == str(users["user"][0])
            replay = await client.post(
                "/api/inventory/movements", headers=users["user"][1], json=payload
            )
            assert replay.json()["id"] == response.json()["id"]
            for restricted in ("WRITE_OFF", "CORRECTION", "REVERSAL"):
                assert (
                    await client.post(
                        "/api/inventory/movements",
                        headers=users["user"][1],
                        json={**payload, "movement_type": restricted},
                    )
                ).status_code == 403

        receipt = await client.post(
            "/api/inventory/movements",
            headers=users["user"][1],
            json={
                "movement_type": "RECEIPT",
                "destination_location_id": str(s[2]),
                "client_request_id": "engineer-receipt",
                "lines": [{"item_id": str(s[1]), "quantity": 1}],
            },
        )
        assert receipt.status_code == 201, receipt.text
        assert receipt.json()["custody_user_id"] is None

        transfer = await client.post(
            "/api/inventory/movements",
            headers=users["user"][1],
            json={
                "movement_type": "TRANSFER",
                "source_location_id": str(s[2]),
                "destination_location_id": str(s[3]),
                "client_request_id": "engineer-transfer",
                "lines": [{"item_id": str(s[1]), "quantity": 1}],
            },
        )
        assert transfer.status_code == 201, transfer.text
        assert transfer.json()["custody_user_id"] is None
        over_return = await client.post(
            "/api/inventory/movements",
            headers=users["user"][1],
            json={
                "movement_type": "RETURN",
                "destination_location_id": str(s[2]),
                "client_request_id": "api-insufficient-custody",
                "lines": [{"item_id": str(s[1]), "quantity": 1}],
            },
        )
        assert over_return.status_code == 409
        assert over_return.json()["detail"]["code"] == "insufficient_custody"
        reversal = f"/api/admin/inventory/movements/{response.json()['id']}/reversal"
        assert (
            await client.post(
                reversal, headers=users["user"][1], json={"client_request_id": "reverse"}
            )
        ).status_code == 403
        reversed_response = await client.post(
            reversal,
            headers=users["admin"][1],
            json={"client_request_id": "reverse"},
        )
        assert reversed_response.status_code == 201
        assert reversed_response.json()["custody_user_id"] == str(users["user"][0])

        for kind in ("ISSUE", "RETURN"):
            admin_payload = {
                "movement_type": kind,
                "client_request_id": f"admin-{kind.lower()}",
                "lines": [{"item_id": str(s[1]), "quantity": 1}],
                (
                    "source_location_id" if kind == "ISSUE" else "destination_location_id"
                ): str(s[2]),
            }
            admin_response = await client.post(
                "/api/inventory/movements",
                headers=users["admin"][1],
                json=admin_payload,
            )
            assert admin_response.status_code == 201, admin_response.text
            assert admin_response.json()["custody_user_id"] is None
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


async def test_new_role_inventory_and_movement_authorization_matrix(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    s = await scenario(db)
    movement = await move(db, s, "RECEIPT", 5, destination=s[2])
    app, users = await api_context(db)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        assert (
            await client.get("/api/inventory/stock", headers=users["manager"][1])
        ).status_code == 200
        assert (
            await client.get("/api/inventory/movements", headers=users["manager"][1])
        ).status_code == 403
        assert (
            await client.post(
                "/api/inventory/movements",
                headers=users["manager"][1],
                json={
                    "movement_type": "RECEIPT",
                    "destination_location_id": str(s[2]),
                    "client_request_id": "manager-forbidden",
                    "lines": [{"item_id": str(s[1]), "quantity": 1}],
                },
            )
        ).status_code == 403

        senior_feed = await client.get(
            "/api/inventory/movements/feed?period=all",
            headers=users["senior"][1],
        )
        assert senior_feed.status_code == 200
        assert str(movement.record.movement.id) in {
            row["id"] for row in senior_feed.json()["items"]
        }
        senior_issue = await client.post(
            "/api/inventory/movements",
            headers=users["senior"][1],
            json={
                "movement_type": "ISSUE",
                "source_location_id": str(s[2]),
                "client_request_id": "senior-custody",
                "lines": [{"item_id": str(s[1]), "quantity": 1}],
            },
        )
        assert senior_issue.status_code == 201, senior_issue.text
        assert senior_issue.json()["custody_user_id"] == str(users["senior"][0])

        for privileged in ("admin", "owner"):
            location = await client.post(
                "/api/admin/inventory/locations",
                headers=users[privileged][1],
                json={
                    "code": uuid.uuid4().hex,
                    "name": f"{privileged} location",
                    "location_type": "WAREHOUSE",
                },
            )
            assert location.status_code == 201, location.text

        assert (
            await client.post(
                "/api/admin/inventory/locations",
                headers=users["senior"][1],
                json={
                    "code": uuid.uuid4().hex,
                    "name": "senior forbidden",
                    "location_type": "WAREHOUSE",
                },
            )
        ).status_code == 403


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
        "ISSUE",
        1,
        source=s[2],
        custody_user_id=users["user"][0],
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
            "/api/inventory/movements/feed",
            params={
                "period": "all",
                "limit": 2,
                "actor_user_id": str(s[0]),
                "before_journal_seq": cursor,
                "snapshot_at": body1["snapshot_at"],
            },
            headers=users["admin"][1],
        )

        assert page2.status_code == 200, page2.text

        body2 = page2.json()

        assert body2["snapshot_at"] == body1["snapshot_at"]

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
    await move(db, s, "RECEIPT", 2, destination=s[2])
    for name in ("Zulu old", "Alpha latest"):
        with patch.object(service, "normalize_inline_text", return_value=name):
            await move(
                db,
                (users["user"][0], *s[1:]),
                "ISSUE",
                1,
                source=s[2],
                custody_user_id=users["user"][0],
            )
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
    await move(db, s, "RECEIPT", 1, destination=s[2])

    supplied_timestamp = (
        anchor
        - timedelta(days=7)
        + timedelta(seconds=1)
    )

    async def supplied_movement_timestamp(
        _db: AsyncSession,
    ) -> datetime:
        return supplied_timestamp

    with patch.object(
        service,
        "_movement_timestamp",
        supplied_movement_timestamp,
    ):
        record = await move(
            db,
            (users["user"][0], *s[1:]),
            "ISSUE",
            1,
            source=s[2],
            custody_user_id=users["user"][0],
        )
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
