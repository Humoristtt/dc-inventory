from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.modules.catalog.enums import (
    AttributeDataType,
    Availability,
    FilterType,
    ItemSort,
    ItemStatus,
    SortOrder,
)
from app.modules.catalog.models import (
    CategoryAttribute,
)
from app.modules.catalog.service import (
    ItemRecord,
)

type FilterValue = str | int | Decimal | bool
type FacetValue = uuid.UUID | str | int | Decimal | bool
type FacetBound = int | Decimal

DEFAULT_FACET_VALUE_LIMIT = 50
MAX_FACET_VALUE_LIMIT = 100
MAX_SEARCH_TOKENS = 12
MAX_QUERY_VALUES = 50
MAX_FILTER_EXPRESSION_LENGTH = 2048

@dataclass(frozen=True, slots=True)
class AttributeFilter:
    attribute_id: uuid.UUID
    key: str
    data_type: AttributeDataType
    filter_type: FilterType
    operator: str
    value: FilterValue


@dataclass(frozen=True, slots=True)
class CatalogQuerySpec:
    tokens: tuple[str, ...]
    category_id: uuid.UUID | None
    category_ids: tuple[uuid.UUID, ...]
    definitions: tuple[CategoryAttribute, ...]
    long_range: bool
    rj45: bool
    category_key: str | None
    status: ItemStatus
    manufacturer_ids: tuple[uuid.UUID, ...]
    availability: Availability
    location_ids: tuple[uuid.UUID, ...]
    attribute_filters: tuple[AttributeFilter, ...]
    sort: ItemSort
    order: SortOrder


@dataclass(frozen=True, slots=True)
class InventorySummary:
    available_count: int
    total_count: int


@dataclass(frozen=True, slots=True)
class CatalogListRecord:
    record: ItemRecord
    inventory: InventorySummary


@dataclass(frozen=True, slots=True)
class CatalogItemPage:
    items: list[CatalogListRecord]
    total: int


@dataclass(frozen=True, slots=True)
class FacetValueRecord:
    value: FacetValue
    count: int
    label: str | None = None
    code: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class FacetRecord:
    key: str
    label: str
    data_type: AttributeDataType
    unit: str | None
    filter_type: FilterType
    values: tuple[FacetValueRecord, ...] = ()
    values_has_more: bool = False
    minimum: FacetBound | None = None
    maximum: FacetBound | None = None
