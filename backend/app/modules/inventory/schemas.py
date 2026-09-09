from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.modules.inventory.enums import (
    LocationStatus,
    LocationType,
    MovementType,
)


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocationCreate(StrictRequestModel):
    code: str = Field(max_length=64)
    name: str = Field(max_length=255)
    location_type: LocationType
    address: str | None = Field(default=None, max_length=2000)


class LocationPatch(StrictRequestModel):
    name: str = Field(max_length=255)
    location_type: LocationType
    address: str | None = Field(default=None, max_length=2000)


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    location_type: LocationType
    address: str | None
    status: LocationStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LocationListOut(BaseModel):
    items: list[LocationOut]
    total: int
    limit: int
    offset: int


class LocationPositionOut(BaseModel):
    location_id: UUID
    code: str
    name: str


class StockBalanceOut(BaseModel):
    id: UUID
    item_id: UUID
    item_name: str
    quantity: int
    location: LocationPositionOut
    updated_at: datetime


class StockBalanceListOut(BaseModel):
    items: list[StockBalanceOut]
    total: int
    limit: int
    offset: int


class InventoryCurrentSummaryOut(BaseModel):
    total_count: int = Field(ge=0)
    locations: list[StockBalanceOut]


class MovementLineCreate(StrictRequestModel):
    item_id: UUID
    quantity: StrictInt = Field(gt=0, le=2**53 - 1)


class MovementCreate(StrictRequestModel):
    movement_type: MovementType
    source_location_id: UUID | None = None
    destination_location_id: UUID | None = None
    original_movement_id: UUID | None = None
    client_request_id: str = Field(min_length=1, max_length=128)
    lines: list[MovementLineCreate] = Field(min_length=1, max_length=500)


class MovementReversalCreate(StrictRequestModel):
    client_request_id: str = Field(min_length=1, max_length=128)


class MovementLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    line_no: int
    item_id: UUID
    quantity: int
    item_name_snapshot: str
    manufacturer_name_snapshot: str | None
    model_snapshot: str | None


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    journal_seq: int
    movement_type: MovementType
    actor_user_id: UUID
    custody_user_id: UUID | None
    actor_display_name_snapshot: str
    source_location_id: UUID | None
    source_location_code_snapshot: str | None
    source_location_name_snapshot: str | None
    destination_location_id: UUID | None
    destination_location_code_snapshot: str | None
    destination_location_name_snapshot: str | None
    original_movement_id: UUID | None
    client_request_id: str
    occurred_at: datetime
    lines: list[MovementLineOut]


class MovementListOut(BaseModel):
    items: list[MovementOut]
    total: int
    limit: int
    offset: int


class MovementCursorListOut(BaseModel):
    snapshot_at: datetime
    items: list[MovementOut]
    limit: int
    next_before_journal_seq: int | None
