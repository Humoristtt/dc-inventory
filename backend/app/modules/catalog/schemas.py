from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.modules.catalog.enums import (
    AccountingMode,
    AttributeDataType,
    FilterType,
    ItemStatus,
)

type AttributeInputValue = str | int | Decimal | float | bool
type AttributeOutputValue = str | int | Decimal | bool
type MetadataValue = str | int | Decimal | bool


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


def _canonicalize_optional_http_url(value: object) -> object:
    if value is None or not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return None

    try:
        return str(_HTTP_URL_ADAPTER.validate_python(stripped))
    except ValueError as error:
        raise ValueError("datasheet_url must be a valid http/https URL") from error


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
    default_accounting_mode: AccountingMode
    sort_order: int
    is_system: bool


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
    manufacturer_part_number: str | None = Field(default=None, max_length=255)
    internal_code: str | None = Field(default=None, max_length=128)
    description: str | None = None
    accounting_mode: AccountingMode | None = None
    comment: str | None = None
    datasheet_url: str | None = Field(default=None, max_length=2048)
    technical_data_source: str | None = None
    attributes: dict[str, AttributeInputValue] = Field(default_factory=dict)

    _canonicalize_datasheet_url = field_validator(
        "datasheet_url",
        mode="before",
    )(_canonicalize_optional_http_url)


class ItemPatch(StrictRequestModel):
    category_key: str | None = Field(default=None, max_length=64)
    manufacturer_id: UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    manufacturer_part_number: str | None = Field(default=None, max_length=255)
    internal_code: str | None = Field(default=None, max_length=128)
    description: str | None = None
    accounting_mode: AccountingMode | None = None
    comment: str | None = None
    datasheet_url: str | None = Field(default=None, max_length=2048)
    technical_data_source: str | None = None
    attributes: dict[str, AttributeInputValue] | None = None

    _canonicalize_datasheet_url = field_validator(
        "datasheet_url",
        mode="before",
    )(_canonicalize_optional_http_url)


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
    manufacturer_part_number: str | None
    internal_code: str | None
    description: str | None
    accounting_mode: AccountingMode
    status: ItemStatus
    comment: str | None
    datasheet_url: str | None
    technical_data_source: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attributes: dict[str, AttributeOutputValue]


class ItemListOut(BaseModel):
    items: list[ItemOut]
    total: int
    limit: int
    offset: int


class DuplicateCheckRequest(StrictRequestModel):
    category_key: str = Field(max_length=64)
    manufacturer_id: UUID | None = None
    manufacturer_part_number: str | None = Field(default=None, max_length=255)
    name: str = Field(max_length=255)
    model: str | None = Field(default=None, max_length=255)
    exclude_item_id: UUID | None = None


class DuplicateCandidateOut(BaseModel):
    item_id: UUID
    name: str
    model: str | None
    manufacturer_id: UUID | None
    manufacturer_name: str | None
    manufacturer_part_number: str | None
    reason: str


class DuplicateCheckOut(BaseModel):
    candidates: list[DuplicateCandidateOut]
