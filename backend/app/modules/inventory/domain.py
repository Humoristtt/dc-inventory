from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.idempotency import (
    normalize_idempotency_key,
)
from app.modules.catalog.models import Item
from app.modules.identity.models import (
    TelegramIdentity,
)
from app.modules.inventory.models import (
    Location,
    Movement,
    MovementLine,
    StockBalance,
)


class InventoryError(RuntimeError):
    code = "inventory_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class InventoryValidationError(InventoryError):
    code = "inventory_validation_error"


class InventoryNotFoundError(InventoryError):
    code = "inventory_not_found"


class InventoryConflictError(InventoryError):
    code = "inventory_conflict"


@dataclass(frozen=True, slots=True)
class LocationPage:
    items: list[Location]
    total: int


@dataclass(frozen=True, slots=True)
class StockBalanceRecord:
    balance: StockBalance
    item: Item
    location: Location


@dataclass(frozen=True, slots=True)
class StockBalancePage:
    items: list[StockBalanceRecord]
    total: int


@dataclass(frozen=True, slots=True)
class MovementRecord:
    movement: Movement
    lines: list[MovementLine]


@dataclass(frozen=True, slots=True)
class MovementPage:
    items: list[MovementRecord]
    total: int


@dataclass(frozen=True, slots=True)
class MovementCursorPage:
    items: list[MovementRecord]
    next_before_journal_seq: int | None


@dataclass(frozen=True, slots=True)
class MovementFeedSnapshot:
    snapshot_at: datetime
    database_snapshot: str


@dataclass(frozen=True, slots=True)
class MovementResult:
    record: MovementRecord
    replayed: bool


def normalize_inline_text(value: str, *, field: str, max_length: int) -> str:
    normalized = normalize_idempotency_key(value)
    if not normalized:
        raise InventoryValidationError(
            f"{field} must not be blank",
            code=f"{field}_required",
        )
    if len(normalized) > max_length:
        raise InventoryValidationError(
            f"{field} exceeds {max_length} characters",
            code=f"{field}_too_long",
        )
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def display_identity(identity: TelegramIdentity) -> str:
    full_name = " ".join(value for value in (identity.first_name, identity.last_name) if value)
    if identity.username:
        return f"{full_name} (@{identity.username})"
    return full_name
