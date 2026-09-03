from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.modules.catalog.enums import AccountingMode
from app.modules.inventory.enums import (
    InventoryUnitState,
    LocationStatus,
    MovementType,
)


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocationCreate(StrictRequestModel):
    code: str = Field(max_length=64)
    name: str = Field(max_length=255)
    description: str | None = None


class LocationOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    status: LocationStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LocationListOut(BaseModel):
    items: list[LocationOut]
    total: int
    limit: int
    offset: int


class UserPositionOut(BaseModel):
    user_id: UUID | None
    display_name: str


class LocationPositionOut(BaseModel):
    location_id: UUID
    code: str
    name: str


class StockBalanceOut(BaseModel):
    id: UUID
    item_id: UUID
    item_name: str
    quantity: int
    location: LocationPositionOut | None
    holder: UserPositionOut | None
    updated_at: datetime


class StockBalanceListOut(BaseModel):
    items: list[StockBalanceOut]
    total: int
    limit: int
    offset: int


class InventoryUnitOut(BaseModel):
    id: UUID
    item_id: UUID
    item_name: str
    serial_number: str | None
    wwn: str | None
    comment: str | None
    state: InventoryUnitState
    location: LocationPositionOut | None
    holder: UserPositionOut | None
    created_at: datetime
    updated_at: datetime


class InventoryUnitListOut(BaseModel):
    items: list[InventoryUnitOut]
    total: int
    limit: int
    offset: int


class MovementLineCreate(StrictRequestModel):
    item_id: UUID | None = None
    quantity: StrictInt | None = None
    inventory_unit_id: UUID | None = None
    serial_number: str | None = Field(default=None, max_length=255)
    wwn: str | None = Field(default=None, max_length=255)
    unit_comment: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "MovementLineCreate":
        supplied_shapes = sum(
            value is not None
            for value in (self.quantity, self.inventory_unit_id, self.serial_number)
        )
        if supplied_shapes != 1:
            raise ValueError(
                "line must contain exactly one of quantity, inventory_unit_id, or serial_number"
            )
        if self.quantity is not None and self.item_id is None:
            raise ValueError("quantity line requires item_id")
        if self.serial_number is not None and self.item_id is None:
            raise ValueError("new serial line requires item_id")
        if self.inventory_unit_id is not None and self.item_id is not None:
            raise ValueError("existing serial line derives item_id from inventory unit")
        if self.serial_number is None and (self.wwn is not None or self.unit_comment is not None):
            raise ValueError("WWN and unit_comment are valid only for a new serial line")
        return self


class MovementCreate(StrictRequestModel):
    movement_type: MovementType
    source_location_id: UUID | None = None
    destination_location_id: UUID | None = None
    source_holder_user_id: UUID | None = None
    destination_holder_user_id: UUID | None = None
    original_movement_id: UUID | None = None
    client_request_id: str = Field(max_length=128)
    purpose: str | None = Field(default=None, max_length=255)
    comment: str | None = None
    lines: list[MovementLineCreate] = Field(min_length=1, max_length=500)


class MovementReversalCreate(StrictRequestModel):
    client_request_id: str = Field(max_length=128)
    purpose: str | None = Field(default=None, max_length=255)
    comment: str | None = None


class MovementLineOut(BaseModel):
    id: UUID
    line_no: int
    item_id: UUID
    accounting_mode: AccountingMode
    inventory_unit_id: UUID | None
    quantity: int | None
    item_name_snapshot: str
    manufacturer_name_snapshot: str | None
    model_snapshot: str | None
    manufacturer_part_number_snapshot: str | None
    serial_number_snapshot: str | None
    wwn_snapshot: str | None


class MovementOut(BaseModel):
    id: UUID
    journal_seq: int
    movement_type: MovementType
    actor_user_id: UUID
    actor_display_name_snapshot: str
    source_location_id: UUID | None
    source_location_code_snapshot: str | None
    source_location_name_snapshot: str | None
    destination_location_id: UUID | None
    destination_location_code_snapshot: str | None
    destination_location_name_snapshot: str | None
    source_holder_user_id: UUID | None
    source_holder_display_name_snapshot: str | None
    destination_holder_user_id: UUID | None
    destination_holder_display_name_snapshot: str | None
    original_movement_id: UUID | None
    client_request_id: str
    purpose: str | None
    comment: str | None
    occurred_at: datetime
    lines: list[MovementLineOut]


class MovementListOut(BaseModel):
    items: list[MovementOut]
    total: int
    limit: int
    offset: int
