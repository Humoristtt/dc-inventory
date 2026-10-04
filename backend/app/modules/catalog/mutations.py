from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.item_validation import _prepare_identity
from app.modules.catalog.models import Item, ItemAttributeValue, Manufacturer
from app.modules.catalog.read_service import get_item_record
from app.modules.catalog.schemas import (
    ItemCreate,
    ItemPatch,
    ManufacturerCreate,
)
from app.modules.catalog.validation import (
    CatalogConflictError,
    CatalogItemInUseError,
    CatalogNotFoundError,
    CatalogValidationError,
    PreparedAttributeValue,
    normalize_comparison,
    normalize_inline_text,
    normalize_optional_inline_text,
)
from app.modules.inventory.models import (
    MovementLine,
    StockBalance,
    UserItemCustodyBalance,
)


async def create_manufacturer(
    db: AsyncSession,
    payload: ManufacturerCreate,
) -> Manufacturer:
    name = normalize_inline_text(payload.name, field="manufacturer_name", max_length=255)
    normalized_name = normalize_comparison(
        name,
        field="manufacturer_name",
        max_length=255,
    )
    existing = await db.scalar(
        select(Manufacturer.id).where(Manufacturer.normalized_name == normalized_name)
    )
    if existing is not None:
        raise CatalogConflictError("manufacturer already exists")

    manufacturer = Manufacturer(name=name, normalized_name=normalized_name)
    db.add(manufacturer)
    await db.flush()
    return manufacturer


def _item_attribute_rows(
    item_id: uuid.UUID,
    category_id: uuid.UUID,
    values: Sequence[PreparedAttributeValue],
) -> list[ItemAttributeValue]:
    return [
        ItemAttributeValue(
            item_id=item_id,
            category_id=category_id,
            category_attribute_id=value.attribute.id,
            text_value=value.text_value,
            integer_value=value.integer_value,
            decimal_value=value.decimal_value,
            boolean_value=value.boolean_value,
            enum_value=value.enum_value,
        )
        for value in values
    ]


async def create_item(db: AsyncSession, payload: ItemCreate) -> uuid.UUID:
    category, values, signature = await _prepare_identity(db, payload)
    item = Item(
        id=uuid.uuid4(),
        category_id=category.id,
        manufacturer_id=payload.manufacturer_id,
        name=normalize_inline_text(payload.name, field="name", max_length=255),
        normalized_name=normalize_comparison(payload.name, field="name", max_length=255),
        model=normalize_optional_inline_text(payload.model, field="model", max_length=255),
        normalized_model=(
            normalize_comparison(payload.model, field="model", max_length=255)
            if payload.model
            else None
        ),
        identity_signature=signature,
        status=ItemStatus.ACTIVE,
    )
    db.add(item)
    db.add_all(_item_attribute_rows(item.id, category.id, values))
    await db.flush()
    return item.id


async def update_item(
    db: AsyncSession, item_id: uuid.UUID, payload: ItemPatch, *, fields_set: set[str]
) -> uuid.UUID:
    item = await db.scalar(select(Item).where(Item.id == item_id).with_for_update())
    if item is None:
        raise CatalogNotFoundError("item not found")
    if "category_key" in fields_set:
        raise CatalogValidationError("category_immutable", "item category cannot be changed")
    if "name" in fields_set and payload.name is None:
        raise CatalogValidationError(
            "name_required",
            "item name must not be null",
        )
    record = await get_item_record(db, item_id)
    data: dict[str, Any] = dict(
        category_key=record.category.key,
        name=item.name,
        model=item.model,
        manufacturer_id=item.manufacturer_id,
        attributes=record.attributes,
    )
    data.update(payload.model_dump(include=fields_set))
    if "attributes" in fields_set and data["attributes"] is None:
        raise CatalogValidationError("attributes_required", "attributes must be an object")
    # reach_m is derived on every edit, including after replacing a reach profile.
    if "attributes" not in fields_set:
        data["attributes"].pop("reach_m", None)
    merged = ItemCreate.model_validate(data)
    category, values, signature = await _prepare_identity(db, merged)
    item.name = normalize_inline_text(merged.name, field="name", max_length=255)
    item.normalized_name = normalize_comparison(item.name, field="name", max_length=255)
    item.model = normalize_optional_inline_text(merged.model, field="model", max_length=255)
    item.normalized_model = (
        normalize_comparison(item.model, field="model", max_length=255) if item.model else None
    )
    item.manufacturer_id = merged.manufacturer_id
    item.identity_signature = signature
    await db.execute(delete(ItemAttributeValue).where(ItemAttributeValue.item_id == item.id))
    db.add_all(_item_attribute_rows(item.id, category.id, values))
    item.updated_at = datetime.now(UTC)
    await db.flush()
    return item.id


async def set_item_archived(
    db: AsyncSession,
    item_id: uuid.UUID,
    *,
    archived: bool,
    now: datetime | None = None,
) -> uuid.UUID:
    item = await db.scalar(select(Item).where(Item.id == item_id).with_for_update())
    if item is None:
        raise CatalogNotFoundError("item not found")

    target_status = ItemStatus.ARCHIVED if archived else ItemStatus.ACTIVE
    if item.status == target_status:
        return item.id

    current_time = now or datetime.now(UTC)
    item.status = target_status
    item.archived_at = current_time if archived else None
    item.updated_at = current_time
    await db.flush()
    return item.id


async def delete_unused_item(
    db: AsyncSession,
    item_id: uuid.UUID,
) -> None:
    item = await db.scalar(select(Item).where(Item.id == item_id).with_for_update())
    if item is None:
        raise CatalogNotFoundError("item not found")

    movement_line_id = await db.scalar(
        select(MovementLine.id).where(MovementLine.item_id == item_id).limit(1)
    )
    if movement_line_id is not None:
        raise CatalogItemInUseError("item has warehouse history and cannot be deleted")

    stock_balance_id = await db.scalar(
        select(StockBalance.id).where(StockBalance.item_id == item_id).limit(1)
    )
    if stock_balance_id is not None:
        raise CatalogItemInUseError("item has warehouse stock state and cannot be deleted")

    custody_balance_id = await db.scalar(
        select(UserItemCustodyBalance.id).where(UserItemCustodyBalance.item_id == item_id).limit(1)
    )
    if custody_balance_id is not None:
        raise CatalogItemInUseError("item has custody state and cannot be deleted")

    # Import locally to keep the catalog model independent from the
    # Procurement bounded module while still enforcing delete safety.
    from app.modules.procurement.models import (
        ProcurementLineCatalogBinding,
        ProcurementRevisionLine,
    )

    procurement_line_id = await db.scalar(
        select(ProcurementRevisionLine.id)
        .where(ProcurementRevisionLine.catalog_item_id == item_id)
        .limit(1)
    )
    procurement_binding_id = await db.scalar(
        select(ProcurementLineCatalogBinding.revision_line_id)
        .where(ProcurementLineCatalogBinding.item_id == item_id)
        .limit(1)
    )
    if procurement_line_id is not None or procurement_binding_id is not None:
        raise CatalogItemInUseError("item has procurement history and cannot be deleted")

    await db.delete(item)
    await db.flush()
