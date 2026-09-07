"""Synthetic Warehouse V2 fixtures; never load operational inventory data."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuthSession
from app.modules.auth.service import hash_session_token
from app.modules.catalog.schemas import ItemCreate
from app.modules.catalog.service import create_item
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.inventory.enums import MovementType
from app.modules.inventory.schemas import LocationCreate, MovementCreate, MovementLineCreate
from app.modules.inventory.service import MovementResult, create_location, create_movement

type Scenario = tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]


def cable_payload(**attributes: Any) -> ItemCreate:
    return ItemCreate(
        category_key="optical_patch_cord",
        name="Synthetic cable",
        attributes={
            "fiber": "MMF",
            "fiber_category": "OM4",
            "connector_a": "LC/UPC",
            "connector_b": "LC/UPC",
            "length_m": "5",
            "construction": "Duplex",
            "color": uuid.uuid4().hex,
            **attributes,
        },
    )


async def actor(
    db: AsyncSession,
    role: UserRole = UserRole.ADMIN,
    access: UserAccessStatus = UserAccessStatus.APPROVED,
) -> tuple[User, str]:
    now = datetime.now(UTC)
    user = User(
        id=uuid.uuid4(),
        role=role,
        access_status=access,
        approved_at=now if access == UserAccessStatus.APPROVED else None,
    )
    token = uuid.uuid4().hex
    db.add_all(
        [
            user,
            TelegramIdentity(
                user=user,
                user_id=user.id,
                telegram_user_id=uuid.uuid4().int % 10**14,
                first_name="Synthetic actor",
            ),
            AuthSession(
                user=user,
                user_id=user.id,
                token_hash=hash_session_token(token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=1),
            ),
        ]
    )
    await db.flush()
    return user, token


async def scenario(db: AsyncSession) -> Scenario:
    user, _ = await actor(db)
    item = await create_item(db, cable_payload())
    locations = [
        await create_location(
            db, LocationCreate(code=uuid.uuid4().hex, name=name, location_type=kind)
        )
        for name, kind in [("Synthetic warehouse", "WAREHOUSE"), ("Synthetic DC", "DATACENTER")]
    ]
    return user.id, item, locations[0].id, locations[1].id


async def move(
    db: AsyncSession,
    scenario: Scenario,
    kind: MovementType | str,
    quantity: int,
    *,
    source: uuid.UUID | None = None,
    destination: uuid.UUID | None = None,
    key: str | None = None,
    original: uuid.UUID | None = None,
) -> MovementResult:
    result = await create_movement(
        db,
        MovementCreate(
            movement_type=kind,
            source_location_id=source,
            destination_location_id=destination,
            client_request_id=key or uuid.uuid4().hex,
            original_movement_id=original,
            lines=[MovementLineCreate(item_id=scenario[1], quantity=quantity)],
        ),
        actor_user_id=scenario[0],
        actor_display_name="Synthetic actor",
    )
    return result
