import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.main import create_app
from app.modules.auth.models import AuthSession
from app.modules.auth.service import hash_session_token
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from tests.test_inventory_postgres import _create_scenario

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)


@pytest.mark.asyncio
async def test_inventory_api_enforces_read_and_mutation_boundaries() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    settings = Settings(database_url=DATABASE_URL, app_env="test")
    application = create_app(settings)
    application.state.db_engine = engine
    now = datetime.now(UTC)
    marker = uuid.uuid4().hex
    tokens = {
        "pending": f"inventory-pending-{marker}",
        "user": f"inventory-user-{marker}",
        "admin": f"inventory-admin-{marker}",
    }

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            scenario = await _create_scenario(db)
            pending_user = User(
                id=uuid.uuid4(),
                role=UserRole.USER,
                access_status=UserAccessStatus.PENDING,
            )
            pending_identity = TelegramIdentity(
                user=pending_user,
                user_id=pending_user.id,
                telegram_user_id=(7_500_000_000 + (uuid.UUID(marker).int % 400_000_000)),
                first_name="Pending",
            )
            db.add_all([pending_user, pending_identity])
            for key, user_id in (
                ("pending", pending_user.id),
                ("user", scenario.holder_one_id),
                ("admin", scenario.actor_id),
            ):
                db.add(
                    AuthSession(
                        user_id=user_id,
                        token_hash=hash_session_token(tokens[key]),
                        created_at=now,
                        last_seen_at=now,
                        expires_at=now + timedelta(hours=1),
                    )
                )
            await db.commit()

        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            anonymous_read = await client.get("/api/inventory/stock")
            anonymous_mutation = await client.post(
                "/api/admin/inventory/movements",
                json={},
            )
            assert anonymous_read.status_code == 401
            assert anonymous_mutation.status_code == 401

            pending_read = await client.get(
                "/api/inventory/locations",
                cookies={settings.auth_cookie_name: tokens["pending"]},
            )
            assert pending_read.status_code == 403

            user_read = await client.get(
                "/api/inventory/locations",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            assert user_read.status_code == 200
            assert str(scenario.location_one_id) in {
                location["id"] for location in user_read.json()["items"]
            }

            movement_body = {
                "movement_type": "RECEIPT",
                "destination_location_id": str(scenario.location_one_id),
                "client_request_id": f"api-receipt-{marker}",
                "purpose": "API authorization test",
                "lines": [
                    {
                        "item_id": str(scenario.quantity_item_id),
                        "quantity": 2,
                    }
                ],
            }
            user_mutation = await client.post(
                "/api/admin/inventory/movements",
                cookies={settings.auth_cookie_name: tokens["user"]},
                json=movement_body,
            )
            assert user_mutation.status_code == 403

            location_response = await client.post(
                "/api/admin/inventory/locations",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json={
                    "code": f"API-{marker[:10]}",
                    "name": "API-created location",
                },
            )
            assert location_response.status_code == 201
            assert location_response.json()["status"] == "ACTIVE"
            api_location_id = location_response.json()["id"]
            archived_location = await client.post(
                f"/api/admin/inventory/locations/{api_location_id}/archive",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            unarchived_location = await client.post(
                f"/api/admin/inventory/locations/{api_location_id}/unarchive",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            assert archived_location.status_code == 200
            assert archived_location.json()["status"] == "ARCHIVED"
            assert unarchived_location.status_code == 200
            assert unarchived_location.json()["status"] == "ACTIVE"

            admin_movement = await client.post(
                "/api/admin/inventory/movements",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json=movement_body,
            )
            replayed_movement = await client.post(
                "/api/admin/inventory/movements",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json=movement_body,
            )
            assert admin_movement.status_code == 201
            assert replayed_movement.status_code == 201
            assert replayed_movement.json()["id"] == admin_movement.json()["id"]
            assert admin_movement.json()["actor_user_id"] == str(scenario.actor_id)
            assert admin_movement.json()["lines"][0]["quantity"] == 2
            assert admin_movement.json()["lines"][0]["line_no"] == 1

            different_payload = {
                **movement_body,
                "lines": [
                    {
                        "item_id": str(scenario.quantity_item_id),
                        "quantity": 3,
                    }
                ],
            }
            idempotency_conflict = await client.post(
                "/api/admin/inventory/movements",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json=different_payload,
            )
            assert idempotency_conflict.status_code == 409
            assert idempotency_conflict.json()["detail"]["code"] == ("idempotency_payload_conflict")

            invalid_quantity = {
                **movement_body,
                "client_request_id": f"api-zero-{marker}",
                "lines": [
                    {
                        "item_id": str(scenario.quantity_item_id),
                        "quantity": 0,
                    }
                ],
            }
            validation_response = await client.post(
                "/api/admin/inventory/movements",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json=invalid_quantity,
            )
            assert validation_response.status_code == 422
            assert validation_response.json()["detail"]["code"] == ("quantity_not_positive")

            for invalid_value in (True, "1", 1.5):
                strict_quantity_response = await client.post(
                    "/api/admin/inventory/movements",
                    cookies={settings.auth_cookie_name: tokens["admin"]},
                    json={
                        **movement_body,
                        "client_request_id": (f"api-strict-{invalid_value!s}-{marker}"),
                        "lines": [
                            {
                                "item_id": str(scenario.quantity_item_id),
                                "quantity": invalid_value,
                            }
                        ],
                    },
                )
                assert strict_quantity_response.status_code == 422

            oversized_location_code = await client.post(
                "/api/admin/inventory/locations",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json={"code": "ß" * 33, "name": "Oversized after casefold"},
            )
            assert oversized_location_code.status_code == 422
            assert oversized_location_code.json()["detail"]["code"] == ("location_code_too_long")

            history = await client.get(
                f"/api/inventory/movements?item_id={scenario.quantity_item_id}",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            stock = await client.get(
                f"/api/inventory/stock?item_id={scenario.quantity_item_id}",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            assert history.status_code == 200
            assert history.json()["total"] == 1
            assert stock.status_code == 200
            assert stock.json()["items"][0]["quantity"] == 2
    finally:
        await engine.dispose()
