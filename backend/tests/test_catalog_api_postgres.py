import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.main import create_app
from app.modules.auth.models import AuthSession
from app.modules.auth.service import hash_session_token
from app.modules.catalog.models import Item, ItemAttributeValue, Manufacturer
from app.modules.catalog.service import normalize_comparison
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)


@pytest.mark.asyncio
async def test_catalog_api_enforces_approved_and_admin_boundaries() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    settings = Settings(database_url=DATABASE_URL, app_env="test")
    application = create_app(settings)
    application.state.db_engine = engine
    marker = uuid.uuid4().hex
    now = datetime.now(UTC)
    contexts = [
        ("pending", UserAccessStatus.PENDING, UserRole.USER),
        ("rejected", UserAccessStatus.REJECTED, UserRole.USER),
        ("blocked", UserAccessStatus.BLOCKED, UserRole.USER),
        ("user", UserAccessStatus.APPROVED, UserRole.USER),
        ("admin", UserAccessStatus.APPROVED, UserRole.ADMIN),
    ]
    user_ids: list[uuid.UUID] = []
    tokens: dict[str, str] = {}
    manufacturer_normalized_name = normalize_comparison(
        f"API Manufacturer {marker}"
    )

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            for index, (key, access_status, role) in enumerate(contexts, start=1):
                user_id = uuid.uuid4()
                token = f"catalog-api-{key}-{marker}"
                user = User(
                    id=user_id,
                    role=role,
                    access_status=access_status,
                    approved_at=(
                        now if access_status == UserAccessStatus.APPROVED else None
                    ),
                )
                db.add_all(
                    [
                        user,
                        TelegramIdentity(
                            id=uuid.uuid4(),
                            user=user,
                            user_id=user_id,
                            telegram_user_id=8_000_000_000 + index,
                            first_name=key.title(),
                        ),
                        AuthSession(
                            id=uuid.uuid4(),
                            user=user,
                            user_id=user_id,
                            token_hash=hash_session_token(token),
                            created_at=now,
                            last_seen_at=now,
                            expires_at=now + timedelta(hours=1),
                        ),
                    ]
                )
                user_ids.append(user_id)
                tokens[key] = token
            await db.commit()

        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.get("/api/catalog/categories")
            assert unauthenticated.status_code == 401

            for key in ("pending", "rejected", "blocked"):
                denied = await client.get(
                    "/api/catalog/categories",
                    cookies={settings.auth_cookie_name: tokens[key]},
                )
                assert denied.status_code == 403

            approved_user = await client.get(
                "/api/catalog/categories",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            approved_admin = await client.get(
                "/api/catalog/categories",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            assert approved_user.status_code == 200
            assert approved_admin.status_code == 200
            assert {
                "sfp",
                "optics",
                "power_cable",
                "nic",
                "disk",
            } <= {item["key"] for item in approved_user.json()}

            user_mutation = await client.post(
                "/api/admin/catalog/manufacturers",
                cookies={settings.auth_cookie_name: tokens["user"]},
                json={"name": f"API Manufacturer {marker}"},
            )
            assert user_mutation.status_code == 403

            manufacturer_response = await client.post(
                "/api/admin/catalog/manufacturers",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json={"name": f"  API   Manufacturer {marker}  "},
            )
            assert manufacturer_response.status_code == 201
            manufacturer_id = manufacturer_response.json()["id"]

            item_response = await client.post(
                "/api/admin/catalog/items",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json={
                    "category_key": "sfp",
                    "manufacturer_id": manufacturer_id,
                    "name": f"API SFP {marker}",
                    "manufacturer_part_number": " API-PN-1 ",
                    "attributes": {
                        "form_factor": "SFP+",
                        "speed_mbps": 10000,
                        "tx_wavelength_nm": "1310.125",
                        "dom_ddm": True,
                    },
                },
            )
            assert item_response.status_code == 201
            item_id = item_response.json()["id"]
            assert item_response.json()["accounting_mode"] == "QUANTITY"
            assert item_response.json()["attributes"]["speed_mbps"] == 10000
            assert item_response.json()["attributes"]["tx_wavelength_nm"] == (
                "1310.1250000000"
            )

            user_item_mutation = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                cookies={settings.auth_cookie_name: tokens["user"]},
                json={"name": "Forbidden"},
            )
            assert user_item_mutation.status_code == 403

            immutable_category = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json={"category_key": "disk"},
            )
            assert immutable_category.status_code == 422
            assert immutable_category.json()["detail"]["code"] == "category_immutable"

            duplicate_response = await client.post(
                "/api/admin/catalog/items/check-duplicates",
                cookies={settings.auth_cookie_name: tokens["admin"]},
                json={
                    "category_key": "sfp",
                    "manufacturer_id": manufacturer_id,
                    "manufacturer_part_number": "api-pn-1",
                    "name": "Ignored",
                },
            )
            assert duplicate_response.status_code == 200
            assert duplicate_response.json()["candidates"][0]["item_id"] == item_id

            archived = await client.post(
                f"/api/admin/catalog/items/{item_id}/archive",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            repeated_archive = await client.post(
                f"/api/admin/catalog/items/{item_id}/archive",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            assert archived.status_code == 200
            assert repeated_archive.status_code == 200
            assert archived.json()["status"] == "ARCHIVED"
            assert (
                repeated_archive.json()["archived_at"]
                == archived.json()["archived_at"]
            )

            active_listing = await client.get(
                "/api/catalog/items?category=sfp",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            archived_listing = await client.get(
                "/api/catalog/items?category=sfp&status=ARCHIVED",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            item_detail = await client.get(
                f"/api/catalog/items/{item_id}",
                cookies={settings.auth_cookie_name: tokens["user"]},
            )
            assert active_listing.status_code == 200
            assert item_id not in {
                item["id"] for item in active_listing.json()["items"]
            }
            assert item_id in {
                item["id"] for item in archived_listing.json()["items"]
            }
            assert item_detail.status_code == 200
            assert item_detail.json()["status"] == "ARCHIVED"

            unarchived = await client.post(
                f"/api/admin/catalog/items/{item_id}/unarchive",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            repeated_unarchive = await client.post(
                f"/api/admin/catalog/items/{item_id}/unarchive",
                cookies={settings.auth_cookie_name: tokens["admin"]},
            )
            assert unarchived.status_code == 200
            assert repeated_unarchive.status_code == 200
            assert unarchived.json()["status"] == "ACTIVE"
            assert repeated_unarchive.json()["archived_at"] is None
    finally:
        async with AsyncSession(engine) as db:
            manufacturer = await db.scalar(
                select(Manufacturer).where(
                    Manufacturer.normalized_name == manufacturer_normalized_name
                )
            )
            if manufacturer is not None:
                item_ids = list(
                    (
                        await db.scalars(
                            select(Item.id).where(
                                Item.manufacturer_id == manufacturer.id
                            )
                        )
                    ).all()
                )
                if item_ids:
                    await db.execute(
                        delete(ItemAttributeValue).where(
                            ItemAttributeValue.item_id.in_(item_ids)
                        )
                    )
                    await db.execute(delete(Item).where(Item.id.in_(item_ids)))
                await db.delete(manufacturer)
            if user_ids:
                await db.execute(
                    delete(AuthSession).where(AuthSession.user_id.in_(user_ids))
                )
                await db.execute(
                    delete(TelegramIdentity).where(
                        TelegramIdentity.user_id.in_(user_ids)
                    )
                )
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()
        await engine.dispose()
