from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalog.enums import (
    AttributeDataType,
    FilterType,
    ItemStatus,
)

type AttributeInputValue = str | int | Decimal | float | bool
type AttributeOutputValue = str | int | Decimal | bool
type MetadataValue = str | int | Decimal | bool


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManufacturerCreate(StrictRequestModel):
    name: str = Field(max_length=255)


class ManufacturerOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ManufacturerListOut(BaseModel):
    items: list[ManufacturerOut]
    total: int
    limit: int
    offset: int


class CategorySummaryOut(BaseModel):
    id: UUID
    key: str
    display_name: str
    description: str | None
    sort_order: int
    is_system: bool
    parent_id: UUID | None


class CategoryAttributeOut(BaseModel):
    id: UUID
    key: str
    label: str
    data_type: AttributeDataType
    unit: str | None
    required: bool
    filterable: bool
    searchable: bool
    card_visible: bool
    detail_visible: bool
    table_visible: bool
    excel_visible: bool
    sort_order: int
    filter_type: FilterType
    allowed_values: list[str] | None
    validation_metadata: dict[str, MetadataValue] | None
    is_system: bool


class CategoryDetailOut(CategorySummaryOut):
    attributes: list[CategoryAttributeOut]


class ItemCreate(StrictRequestModel):
    category_key: str = Field(max_length=64)
    manufacturer_id: UUID | None = None
    name: str = Field(max_length=255)
    model: str | None = Field(default=None, max_length=255)
    attributes: dict[str, AttributeInputValue] = Field(default_factory=dict)


class ItemPatch(StrictRequestModel):
    category_key: str | None = Field(default=None, max_length=64)
    manufacturer_id: UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    attributes: dict[str, AttributeInputValue] | None = None


class ItemCategoryOut(BaseModel):
    id: UUID
    key: str
    display_name: str


class ItemManufacturerOut(BaseModel):
    id: UUID
    name: str


class ItemOut(BaseModel):
    id: UUID
    category: ItemCategoryOut
    manufacturer: ItemManufacturerOut | None
    name: str
    model: str | None
    status: ItemStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attributes: dict[str, AttributeOutputValue]


class InventorySummaryOut(BaseModel):
    available_count: int = Field(ge=0)
    total_count: int = Field(ge=0)


class ItemListEntryOut(ItemOut):
    inventory: InventorySummaryOut


class ItemListOut(BaseModel):
    items: list[ItemListEntryOut]
    total: int
    limit: int
    offset: int


type FacetMachineValue = UUID | bool | int | Decimal | str
type FacetBoundValue = int | Decimal


class FacetValueOut(BaseModel):
    value: FacetMachineValue
    count: int = Field(ge=1)
    label: str | None = None
    code: str | None = None
    name: str | None = None


class FacetOut(BaseModel):
    key: str
    label: str
    data_type: AttributeDataType
    unit: str | None
    filter_type: FilterType
    values: list[FacetValueOut] = Field(default_factory=list)
    values_has_more: bool = False
    min: FacetBoundValue | None = None
    max: FacetBoundValue | None = None


class FacetListOut(BaseModel):
    facets: list[FacetOut]


class DuplicateCheckRequest(ItemCreate):
    category_key: str = Field(max_length=64)
    manufacturer_id: UUID | None = None
    name: str = Field(max_length=255)
    model: str | None = Field(default=None, max_length=255)
    exclude_item_id: UUID | None = None


class DuplicateCandidateOut(BaseModel):
    item_id: UUID
    name: str
    model: str | None
    manufacturer_id: UUID | None
    manufacturer_name: str | None
    reason: str


class DuplicateCheckOut(BaseModel):
    candidates: list[DuplicateCandidateOut]
