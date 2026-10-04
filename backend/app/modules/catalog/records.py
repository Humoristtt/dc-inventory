from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    Manufacturer,
)


@dataclass(frozen=True, slots=True)
class CategoryRecord:
    category: Category
    attributes: list[CategoryAttribute]


@dataclass(frozen=True, slots=True)
class ItemRecord:
    item: Item
    category: Category
    manufacturer: Manufacturer | None
    attributes: dict[str, str | int | Decimal | bool]


@dataclass(frozen=True, slots=True)
class ItemPage:
    items: list[ItemRecord]
    total: int


@dataclass(frozen=True, slots=True)
class ManufacturerPage:
    items: list[Manufacturer]
    total: int


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    item: Item
    manufacturer: Manufacturer | None
    reason: str


@dataclass(frozen=True, slots=True)
class ValidatedItemDraft:
    category: Category
    manufacturer: Manufacturer | None
    name: str
    model: str | None
    attributes: dict[str, str | int | Decimal | bool]
    identity_signature: str
