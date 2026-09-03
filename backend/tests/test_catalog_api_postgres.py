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
from app.modules.catalog.enums import AccountingMode
from app.modules.catalog.models import (
    Category,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.service import normalize_comparison
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.inventory.enums import InventoryUnitState, LocationStatus
from app.modules.inventory.models import InventoryUnit, Location
from app.modules.inventory.service import normalize_identity

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)

def _auth_headers(
    settings: Settings,
    token: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        "Cookie": f"{settings.auth_cookie_name}={token}",
    }
    if extra is not None:
        headers.update(extra)
    return headers



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
    user_ids_by_key: dict[str, uuid.UUID] = {}
    tokens: dict[str, str] = {}
    privacy_location_id: uuid.UUID | None = None
    facet_item_ids: list[uuid.UUID] = []
    facet_manufacturer_ids: list[uuid.UUID] = []
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
                user_ids_by_key[key] = user_id
                tokens[key] = token
            await db.commit()

        transport = ASGITransport(app=application)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": settings.telegram_web_app_url},
        ) as client:
            unauthenticated = await client.get("/api/catalog/categories")
            assert unauthenticated.status_code == 401

            async with AsyncClient(
                transport=ASGITransport(app=application),
                base_url="http://test",
            ) as originless_client:
                missing_origin = await originless_client.post(
                    "/api/admin/catalog/manufacturers",
                    headers=_auth_headers(settings, tokens["admin"]),
                    json={"name": f"Missing Origin {marker}"},
                )
                foreign_origin = await originless_client.post(
                    "/api/admin/catalog/manufacturers",
                    headers=_auth_headers(settings, tokens["admin"], {"Origin": "https://evil.example"}),
                    json={"name": f"Foreign Origin {marker}"},
                )

            assert missing_origin.status_code == 403
            assert missing_origin.json()["detail"] == (
                "cross-origin authenticated mutation forbidden"
            )
            assert foreign_origin.status_code == 403
            assert foreign_origin.json()["detail"] == (
                "cross-origin authenticated mutation forbidden"
            )

            for key in ("pending", "rejected", "blocked"):
                denied = await client.get(
                    "/api/catalog/categories",
                    headers=_auth_headers(settings, tokens[key]),
                )
                assert denied.status_code == 403

            approved_user = await client.get(
                "/api/catalog/categories",
                headers=_auth_headers(settings, tokens["user"]),
            )
            approved_admin = await client.get(
                "/api/catalog/categories",
                headers=_auth_headers(settings, tokens["admin"]),
            )
            assert approved_user.status_code == 200
            assert approved_admin.status_code == 200
            assert {
                "sfp",
                "optics",
                "copper_network_cable",
                "power_cable",
                "nic",
                "disk",
            } <= {item["key"] for item in approved_user.json()}

            user_mutation = await client.post(
                "/api/admin/catalog/manufacturers",
                headers=_auth_headers(settings, tokens["user"]),
                json={"name": f"API Manufacturer {marker}"},
            )
            assert user_mutation.status_code == 403

            manufacturer_response = await client.post(
                "/api/admin/catalog/manufacturers",
                headers=_auth_headers(settings, tokens["admin"]),
                json={"name": f"  API   Manufacturer {marker}  "},
            )
            assert manufacturer_response.status_code == 201
            manufacturer_id = manufacturer_response.json()["id"]

            manufacturer_search = await client.get(
                "/api/catalog/manufacturers",
                params={
                    "q": f"  API   Manufacturer {marker}  ",
                    "limit": 1,
                    "offset": 0,
                },
                headers=_auth_headers(settings, tokens["user"]),
            )
            assert manufacturer_search.status_code == 200
            assert manufacturer_search.json()["total"] == 1
            assert manufacturer_search.json()["items"] == [
                manufacturer_response.json()
            ]
            assert manufacturer_search.json()["limit"] == 1
            assert manufacturer_search.json()["offset"] == 0

            contradictory_item = await client.post(
                "/api/admin/catalog/items",
                headers=_auth_headers(settings, tokens["admin"]),
                json={
                    "category_key": "sfp",
                    "manufacturer_id": manufacturer_id,
                    "name": f"Contradictory API SFP {marker}",
                    "attributes": {
                        "speed_mbps": 10000,
                        "speed_profile": "10/25 Гбит/с",
                    },
                },
            )
            assert contradictory_item.status_code == 422
            assert contradictory_item.json()["detail"]["code"] == (
                "profile_scalar_mismatch"
            )

            item_response = await client.post(
                "/api/admin/catalog/items",
                headers=_auth_headers(settings, tokens["admin"]),
                json={
                    "category_key": "sfp",
                    "manufacturer_id": manufacturer_id,
                    "name": f"API SFP {marker}",
                    "manufacturer_part_number": " API-PN-1 ",
                    "datasheet_url": (
                        "  https://Example.COM/docs?q=a  b  "
                    ),
                    "attributes": {
                        "form_factor": "SFP+",
                        "speed_mbps": 10000,
                        "speed_profile": "10 Гбит/с",
                        "reach_profile": "OM3: до 70 м\nOM4: до 100 м",
                        "wavelength_profile": "1310 нм",
                        "nominal_wavelength_nm": "1310",
                        "tx_wavelength_nm": "1310.125",
                        "dom_ddm": True,
                    },
                },
            )
            assert item_response.status_code == 201
            item_id = item_response.json()["id"]
            assert item_response.json()["accounting_mode"] == "QUANTITY"
            assert item_response.json()["datasheet_url"] == (
                "https://example.com/docs?q=a%20%20b"
            )
            assert item_response.json()["attributes"]["speed_mbps"] == 10000
            assert item_response.json()["attributes"]["tx_wavelength_nm"] == (
                "1310.1250000000"
            )
            assert item_response.json()["attributes"]["reach_profile"] == (
                "OM3: до 70 м\nOM4: до 100 м"
            )
            assert item_response.json()["attributes"]["nominal_wavelength_nm"] == (
                "1310.0000000000"
            )

            privacy_item_response = await client.post(
                "/api/admin/catalog/items",
                headers=_auth_headers(settings, tokens["admin"]),
                json={
                    "category_key": "sfp",
                    "manufacturer_id": manufacturer_id,
                    "name": f"API privacy serial {marker}",
                    "accounting_mode": "SERIAL",
                    "attributes": {
                        "form_factor": "SFP+",
                        "speed_mbps": 10000,
                        "speed_profile": "10 Гбит/с",
                    },
                },
            )
            assert privacy_item_response.status_code == 201
            privacy_item_id = uuid.UUID(
                privacy_item_response.json()["id"]
            )

            own_serial = f"API-OWN-{marker}"
            own_wwn = f"5000-OWN-{marker}"
            stored_serial = f"API-STORED-{marker}"
            stored_wwn = f"5000-STORED-{marker}"
            foreign_serial = f"API-FOREIGN-{marker}"
            foreign_wwn = f"5000-FOREIGN-{marker}"
            written_serial = f"API-WRITTEN-{marker}"
            voided_serial = f"API-VOIDED-{marker}"

            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                privacy_location = Location(
                    id=uuid.uuid4(),
                    code=f"F32-{marker[:8]}",
                    normalized_code=f"f32-{marker[:8]}",
                    name="F32 privacy warehouse",
                    status=LocationStatus.ACTIVE,
                )
                privacy_location_id = privacy_location.id
                db.add(privacy_location)
                await db.flush()

                db.add_all(
                    [
                        InventoryUnit(
                            item_id=privacy_item_id,
                            serial_number=own_serial,
                            normalized_serial_number=normalize_identity(
                                own_serial,
                                field="serial_number",
                                max_length=255,
                            ),
                            wwn=own_wwn,
                            normalized_wwn=normalize_identity(
                                own_wwn,
                                field="wwn",
                                max_length=255,
                            ),
                            state=InventoryUnitState.ISSUED,
                            current_holder_user_id=user_ids_by_key["user"],
                        ),
                        InventoryUnit(
                            item_id=privacy_item_id,
                            serial_number=stored_serial,
                            normalized_serial_number=normalize_identity(
                                stored_serial,
                                field="serial_number",
                                max_length=255,
                            ),
                            wwn=stored_wwn,
                            normalized_wwn=normalize_identity(
                                stored_wwn,
                                field="wwn",
                                max_length=255,
                            ),
                            state=InventoryUnitState.STORED,
                            current_location_id=privacy_location.id,
                        ),
                        InventoryUnit(
                            item_id=privacy_item_id,
                            serial_number=foreign_serial,
                            normalized_serial_number=normalize_identity(
                                foreign_serial,
                                field="serial_number",
                                max_length=255,
                            ),
                            wwn=foreign_wwn,
                            normalized_wwn=normalize_identity(
                                foreign_wwn,
                                field="wwn",
                                max_length=255,
                            ),
                            state=InventoryUnitState.ISSUED,
                            current_holder_user_id=user_ids_by_key["admin"],
                        ),
                        InventoryUnit(
                            item_id=privacy_item_id,
                            serial_number=written_serial,
                            normalized_serial_number=normalize_identity(
                                written_serial,
                                field="serial_number",
                                max_length=255,
                            ),
                            state=InventoryUnitState.WRITTEN_OFF,
                        ),
                        InventoryUnit(
                            item_id=privacy_item_id,
                            serial_number=voided_serial,
                            normalized_serial_number=normalize_identity(
                                voided_serial,
                                field="serial_number",
                                max_length=255,
                            ),
                            state=InventoryUnitState.VOIDED,
                        ),
                    ]
                )
                await db.commit()

            async def catalog_search_total(
                query: str,
                *,
                token: str,
            ) -> int:
                response = await client.get(
                    "/api/catalog/items",
                    params={"q": query},
                    headers=_auth_headers(settings, token),
                )
                assert response.status_code == 200
                return int(response.json()["total"])

            # Regular USER may use only identities of units currently
            # issued to that exact internal User.id.
            assert await catalog_search_total(
                own_serial,
                token=tokens["user"],
            ) == 1
            assert await catalog_search_total(
                own_wwn,
                token=tokens["user"],
            ) == 1

            assert await catalog_search_total(
                stored_serial,
                token=tokens["user"],
            ) == 0
            assert await catalog_search_total(
                stored_wwn,
                token=tokens["user"],
            ) == 0
            assert await catalog_search_total(
                foreign_serial,
                token=tokens["user"],
            ) == 0
            assert await catalog_search_total(
                foreign_wwn,
                token=tokens["user"],
            ) == 0
            assert await catalog_search_total(
                written_serial,
                token=tokens["user"],
            ) == 0
            assert await catalog_search_total(
                voided_serial,
                token=tokens["user"],
            ) == 0

            # ADMIN retains the full operational serial/WWN search.
            for admin_query in (
                own_serial,
                own_wwn,
                stored_serial,
                stored_wwn,
                foreign_serial,
                foreign_wwn,
                written_serial,
                voided_serial,
            ):
                assert await catalog_search_total(
                    admin_query,
                    token=tokens["admin"],
                ) == 1

            # Facets must not reintroduce the same oracle.
            user_foreign_facets = await client.get(
                "/api/catalog/items/facets",
                params={"q": foreign_serial},
                headers=_auth_headers(settings, tokens["user"]),
            )
            admin_foreign_facets = await client.get(
                "/api/catalog/items/facets",
                params={"q": foreign_serial},
                headers=_auth_headers(settings, tokens["admin"]),
            )

            assert user_foreign_facets.status_code == 200
            assert admin_foreign_facets.status_code == 200

            user_category_facet = next(
                facet
                for facet in user_foreign_facets.json()["facets"]
                if facet["key"] == "category"
            )
            admin_category_facet = next(
                facet
                for facet in admin_foreign_facets.json()["facets"]
                if facet["key"] == "category"
            )

            assert user_category_facet["values"] == []
            assert any(
                value["value"] == "sfp"
                for value in admin_category_facet["values"]
            )

            # F34: the HTTP facet contract must expose bounded,
            # independently pageable values without losing candidates.
            facet_marker = f"f34api{uuid.uuid4().hex}"

            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                sfp_category = await db.scalar(
                    select(Category).where(Category.key == "sfp")
                )
                assert sfp_category is not None

                for index in range(61):
                    suffix = f"{index:03d}"

                    manufacturer_name = (
                        f"F34 API Manufacturer {suffix} "
                        f"{facet_marker}"
                    )
                    facet_manufacturer = Manufacturer(
                        id=uuid.uuid4(),
                        name=manufacturer_name,
                        normalized_name=normalize_comparison(
                            manufacturer_name
                        ),
                    )

                    item_name = (
                        f"F34 API Item {suffix} {facet_marker}"
                    )
                    item = Item(
                        id=uuid.uuid4(),
                        category_id=sfp_category.id,
                        manufacturer_id=facet_manufacturer.id,
                        name=item_name,
                        normalized_name=normalize_comparison(
                            item_name
                        ),
                        accounting_mode=AccountingMode.QUANTITY,
                    )

                    facet_manufacturer_ids.append(
                        facet_manufacturer.id
                    )
                    facet_item_ids.append(item.id)
                    db.add_all([facet_manufacturer, item])

                await db.commit()

            first_facet_page = await client.get(
                "/api/catalog/items/facets",
                params={
                    "category": "sfp",
                    "q": facet_marker,
                    "facet": "manufacturer",
                    "facet_limit": 50,
                },
                headers=_auth_headers(settings, tokens["user"]),
            )
            assert first_facet_page.status_code == 200

            first_payload = first_facet_page.json()
            assert len(first_payload["facets"]) == 1

            first_manufacturers = first_payload["facets"][0]
            assert first_manufacturers["key"] == "manufacturer"
            assert len(first_manufacturers["values"]) == 50
            assert first_manufacturers["values_has_more"] is True

            second_facet_page = await client.get(
                "/api/catalog/items/facets",
                params={
                    "category": "sfp",
                    "q": facet_marker,
                    "facet": "manufacturer",
                    "facet_limit": 50,
                    "facet_offset": 50,
                },
                headers=_auth_headers(settings, tokens["user"]),
            )
            assert second_facet_page.status_code == 200

            second_payload = second_facet_page.json()
            assert len(second_payload["facets"]) == 1

            second_manufacturers = second_payload["facets"][0]
            assert second_manufacturers["key"] == "manufacturer"
            assert len(second_manufacturers["values"]) == 11
            assert second_manufacturers["values_has_more"] is False

            returned_manufacturer_ids = {
                str(value["value"])
                for value in (
                    *first_manufacturers["values"],
                    *second_manufacturers["values"],
                )
            }
            expected_manufacturer_ids = {
                str(identifier)
                for identifier in facet_manufacturer_ids
            }

            assert len(returned_manufacturer_ids) == 61
            assert (
                returned_manufacturer_ids
                == expected_manufacturer_ids
            )

            invalid_facet_limit = await client.get(
                "/api/catalog/items/facets",
                params={
                    "category": "sfp",
                    "q": facet_marker,
                    "facet": "manufacturer",
                    "facet_limit": 0,
                },
                headers=_auth_headers(settings, tokens["user"]),
            )
            assert invalid_facet_limit.status_code == 422

            stage7_listing = await client.get(
                "/api/catalog/items",
                params={"q": "api-pn-1", "category": "sfp"},
                headers=_auth_headers(settings, tokens["user"]),
            )
            assert stage7_listing.status_code == 200
            listed = next(item for item in stage7_listing.json()["items"] if item["id"] == item_id)
            assert listed["inventory"] == {
                "available_count": 0,
                "custody_count": 0,
                "total_count": 0,
            }

            stage7_facets = await client.get(
                "/api/catalog/items/facets",
                params=[
                    ("category", "sfp"),
                    ("manufacturer_id", manufacturer_id),
                    ("filter", "speed_mbps:eq:10000"),
                ],
                headers=_auth_headers(settings, tokens["admin"]),
            )
            assert stage7_facets.status_code == 200
            facet_keys = {facet["key"] for facet in stage7_facets.json()["facets"]}
            assert {"manufacturer", "availability", "location", "speed_mbps"} <= facet_keys
            assert "vendor_compatibility" not in facet_keys

            pending_facets = await client.get(
                "/api/catalog/items/facets",
                headers=_auth_headers(settings, tokens["pending"]),
            )
            assert pending_facets.status_code == 403

            controlled_errors = [
                ({"filter": "speed_mbps:eq:10000"}, "filter_category_required"),
                ({"category": "sfp", "filter": "missing:eq:value"}, "filter_unknown_attribute"),
                ({"availability": "maybe"}, "availability_invalid"),
                ({"sort": "random"}, "sort_invalid"),
                ({"order": "random"}, "order_invalid"),
            ]
            for params, expected_code in controlled_errors:
                invalid = await client.get(
                    "/api/catalog/items",
                    params=params,
                    headers=_auth_headers(settings, tokens["user"]),
                )
                assert invalid.status_code == 422
                assert invalid.json()["detail"]["code"] == expected_code

            canonical_url_patch = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["admin"]),
                json={
                    "datasheet_url": (
                        "  HTTPS://Example.COM/updated path  "
                    )
                },
            )
            assert canonical_url_patch.status_code == 200
            assert canonical_url_patch.json()["datasheet_url"] == (
                "https://example.com/updated%20path"
            )

            user_item_mutation = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["user"]),
                json={"name": "Forbidden"},
            )
            assert user_item_mutation.status_code == 403

            immutable_category = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["admin"]),
                json={"category_key": "disk"},
            )
            assert immutable_category.status_code == 422
            assert immutable_category.json()["detail"]["code"] == "category_immutable"

            consistent_attributes_patch = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["admin"]),
                json={
                    "attributes": {
                        "speed_mbps": 10000,
                        "speed_profile": "10 Гбит/с",
                        "reach_profile": "до 20 км",
                        "reach_m": 20000,
                        "wavelength_profile": "1310 нм",
                        "nominal_wavelength_nm": "1310",
                    }
                },
            )
            assert consistent_attributes_patch.status_code == 200
            assert (
                consistent_attributes_patch.json()["attributes"]["reach_m"]
                == 20000
            )

            contradictory_attributes_patch = await client.patch(
                f"/api/admin/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["admin"]),
                json={
                    "attributes": {
                        "speed_mbps": 10000,
                        "speed_profile": "10 Гбит/с",
                        "reach_profile": "до 20 км",
                        "reach_m": 10000,
                        "wavelength_profile": "1310 нм",
                        "nominal_wavelength_nm": "1310",
                    }
                },
            )
            assert contradictory_attributes_patch.status_code == 422
            assert contradictory_attributes_patch.json()["detail"]["code"] == (
                "profile_scalar_mismatch"
            )

            after_failed_patch = await client.get(
                f"/api/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["admin"]),
            )
            assert after_failed_patch.status_code == 200
            assert after_failed_patch.json()["attributes"]["reach_m"] == 20000
            assert after_failed_patch.json()["attributes"]["reach_profile"] == (
                "до 20 км"
            )

            duplicate_response = await client.post(
                "/api/admin/catalog/items/check-duplicates",
                headers=_auth_headers(settings, tokens["admin"]),
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
                headers=_auth_headers(settings, tokens["admin"]),
            )
            repeated_archive = await client.post(
                f"/api/admin/catalog/items/{item_id}/archive",
                headers=_auth_headers(settings, tokens["admin"]),
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
                headers=_auth_headers(settings, tokens["user"]),
            )
            archived_listing = await client.get(
                "/api/catalog/items?category=sfp&status=ARCHIVED",
                headers=_auth_headers(settings, tokens["user"]),
            )
            item_detail = await client.get(
                f"/api/catalog/items/{item_id}",
                headers=_auth_headers(settings, tokens["user"]),
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
                headers=_auth_headers(settings, tokens["admin"]),
            )
            repeated_unarchive = await client.post(
                f"/api/admin/catalog/items/{item_id}/unarchive",
                headers=_auth_headers(settings, tokens["admin"]),
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
                        delete(InventoryUnit).where(
                            InventoryUnit.item_id.in_(item_ids)
                        )
                    )
                    await db.execute(
                        delete(ItemAttributeValue).where(
                            ItemAttributeValue.item_id.in_(item_ids)
                        )
                    )
                    await db.execute(delete(Item).where(Item.id.in_(item_ids)))
                await db.delete(manufacturer)
            if facet_item_ids:
                await db.execute(
                    delete(Item).where(
                        Item.id.in_(facet_item_ids)
                    )
                )
            if facet_manufacturer_ids:
                await db.execute(
                    delete(Manufacturer).where(
                        Manufacturer.id.in_(
                            facet_manufacturer_ids
                        )
                    )
                )
            if privacy_location_id is not None:
                await db.execute(
                    delete(Location).where(
                        Location.id == privacy_location_id
                    )
                )
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
