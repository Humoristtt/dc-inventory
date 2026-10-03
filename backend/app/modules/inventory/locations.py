from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.normalization import identity_text
from app.modules.inventory.domain import (
    InventoryConflictError,
    InventoryNotFoundError,
    InventoryValidationError,
    normalize_inline_text,
    normalize_optional_text,
)
from app.modules.inventory.enums import LocationStatus
from app.modules.inventory.models import Location, StockBalance
from app.modules.inventory.schemas import LocationCreate, LocationPatch


async def create_location(db: AsyncSession, payload: LocationCreate) -> Location:
    code = normalize_inline_text(payload.code, field="code", max_length=64)
    normalized_code = identity_text(code)
    if len(normalized_code) > 64:
        raise InventoryValidationError("normalized location code exceeds 64 characters")
    location = Location(
        code=code,
        normalized_code=normalized_code,
        name=normalize_inline_text(payload.name, field="name", max_length=255),
        location_type=payload.location_type,
        address=normalize_optional_text(payload.address),
        status=LocationStatus.ACTIVE,
    )
    db.add(location)
    await db.flush()
    return location


async def update_location(
    db: AsyncSession, location_id: uuid.UUID, payload: LocationPatch
) -> Location:
    location = await db.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if location is None:
        raise InventoryNotFoundError("location not found")
    location.name = normalize_inline_text(payload.name, field="name", max_length=255)
    location.location_type = payload.location_type
    location.address = normalize_optional_text(payload.address)
    await db.flush()
    return location


async def set_location_archived(
    db: AsyncSession, location_id: uuid.UUID, *, archived: bool, now: datetime | None = None
) -> Location:
    location = await db.scalar(select(Location).where(Location.id == location_id).with_for_update())
    if location is None:
        raise InventoryNotFoundError("location not found")
    if archived and await db.scalar(
        select(StockBalance.id).where(StockBalance.location_id == location_id).limit(1)
    ):
        raise InventoryConflictError(
            "location with stock cannot be archived", code="location_not_empty"
        )
    location.status = LocationStatus.ARCHIVED if archived else LocationStatus.ACTIVE
    location.archived_at = (now or datetime.now(UTC)) if archived else None
    await db.flush()
    return location
