from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.catalog.enums import AttributeDataType, ItemStatus
from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.schemas import (
    DuplicateCheckRequest,
    ItemCreate,
    ItemPatch,
    ManufacturerCreate,
)
from app.modules.catalog.validation import (
    MAX_DECIMAL_INTEGRAL_DIGITS,
    MAX_DECIMAL_SCALE,
    MAX_SAFE_INTEGER,
    MIN_SAFE_INTEGER,
    CatalogConflictError,
    CatalogError,
    CatalogItemInUseError,
    CatalogNotFoundError,
    CatalogSchemaError,
    CatalogValidationError,
    PreparedAttributeValue,
    _normalize_category_key,
    normalize_comparison,
    normalize_inline_text,
    normalize_optional_inline_text,
    normalize_optional_text,
    prepare_attribute_filter_value,
    validate_attribute_values,
)
from app.modules.inventory.models import (
    MovementLine,
    StockBalance,
    UserItemCustodyBalance,
)

__all__ = (
    "MAX_DECIMAL_INTEGRAL_DIGITS",
    "MAX_DECIMAL_SCALE",
    "MAX_SAFE_INTEGER",
    "MIN_SAFE_INTEGER",
    "CatalogConflictError",
    "CatalogError",
    "CatalogItemInUseError",
    "CatalogNotFoundError",
    "CatalogSchemaError",
    "CatalogValidationError",
    "normalize_optional_text",
    "prepare_attribute_filter_value",
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


@dataclass(frozen=True, slots=True)
class _PreparedItemIdentity:
    category: Category
    manufacturer: Manufacturer | None
    values: list[PreparedAttributeValue]
    identity_signature: str


@dataclass(frozen=True, slots=True)
class ItemCreateValidationContext:
    """Catalog-owned metadata used to validate one or more item drafts."""

    categories_by_key: dict[str, Category]
    manufacturers_by_id: dict[uuid.UUID, Manufacturer]
    attributes_by_category_id: dict[uuid.UUID, list[CategoryAttribute]]

    def prepare_identity(self, payload: ItemCreate) -> _PreparedItemIdentity:
        from app.modules.catalog.configuration import LEAVES, MANUFACTURED_LEAVES
        from app.modules.catalog.normalization import item_signature, normalize_reach

        normalized_key = _normalize_category_key(payload.category_key)
        category = self.categories_by_key.get(normalized_key)
        if category is None:
            raise CatalogNotFoundError("category not found")
        if category.parent_id is None or category.key not in LEAVES:
            raise CatalogValidationError(
                "leaf_category_required", "items require a fixed leaf category"
            )

        manufacturer = None
        if payload.manufacturer_id is not None:
            manufacturer = self.manufacturers_by_id.get(payload.manufacturer_id)
            if manufacturer is None:
                raise CatalogNotFoundError("manufacturer not found")
        if category.key in MANUFACTURED_LEAVES and (
            manufacturer is None or not payload.model or not payload.model.strip()
        ):
            raise CatalogValidationError("identity_required", "manufacturer and model are required")

        attributes = dict(payload.attributes)
        if category.key.startswith("transceiver_"):
            try:
                derived = normalize_reach(str(attributes.get("reach", "")))
            except ValueError as error:
                raise CatalogValidationError("reach_invalid", str(error)) from error
            if "reach_m" in attributes and attributes["reach_m"] != derived:
                raise CatalogValidationError(
                    "reach_mismatch", "normalized reach contradicts display value"
                )
            attributes["reach_m"] = derived

        values = validate_attribute_values(
            category.id,
            self.attributes_by_category_id.get(category.id, []),
            attributes,
        )
        normalized_attributes = {
            value.attribute.key: next(
                candidate
                for candidate in (
                    value.text_value,
                    value.integer_value,
                    value.decimal_value,
                    value.boolean_value,
                    value.enum_value,
                )
                if candidate is not None
            )
            for value in values
        }
        signature = item_signature(
            category.key,
            manufacturer.name if manufacturer else None,
            payload.model,
            normalized_attributes,
        )
        return _PreparedItemIdentity(
            category=category,
            manufacturer=manufacturer,
            values=values,
            identity_signature=signature,
        )

    def validate(self, payload: ItemCreate) -> ValidatedItemDraft:
        prepared = self.prepare_identity(payload)
        attributes = {
            value.attribute.key: next(
                candidate
                for candidate in (
                    value.text_value,
                    value.integer_value,
                    value.decimal_value,
                    value.boolean_value,
                    value.enum_value,
                )
                if candidate is not None
            )
            for value in prepared.values
        }
        return ValidatedItemDraft(
            category=prepared.category,
            manufacturer=prepared.manufacturer,
            name=normalize_inline_text(payload.name, field="name", max_length=255),
            model=normalize_optional_inline_text(payload.model, field="model", max_length=255),
            attributes=attributes,
            identity_signature=prepared.identity_signature,
        )


async def get_category_by_key(
    db: AsyncSession,
    category_key: str,
) -> Category:
    normalized_key = _normalize_category_key(category_key)
    category = await db.scalar(select(Category).where(Category.key == normalized_key))
    if category is None:
        raise CatalogNotFoundError("category not found")
    return category


async def _get_category_attributes(
    db: AsyncSession,
    category_id: uuid.UUID,
) -> list[CategoryAttribute]:
    result = await db.scalars(
        select(CategoryAttribute)
        .where(CategoryAttribute.category_id == category_id)
        .order_by(CategoryAttribute.sort_order, CategoryAttribute.key)
    )
    return list(result.all())


async def _get_manufacturer(
    db: AsyncSession,
    manufacturer_id: uuid.UUID | None,
) -> Manufacturer | None:
    if manufacturer_id is None:
        return None
    manufacturer = await db.get(Manufacturer, manufacturer_id)
    if manufacturer is None:
        raise CatalogNotFoundError("manufacturer not found")
    return manufacturer


async def load_item_create_validation_context(
    db: AsyncSession,
    payloads: Sequence[ItemCreate],
) -> ItemCreateValidationContext:
    """Load shared Catalog validation metadata in bounded batch queries."""
    category_keys = sorted({_normalize_category_key(payload.category_key) for payload in payloads})
    manufacturer_ids = sorted(
        {payload.manufacturer_id for payload in payloads if payload.manufacturer_id is not None},
        key=str,
    )

    categories: list[Category] = []
    if category_keys:
        categories = list(
            (
                await db.scalars(
                    select(Category).where(Category.key.in_(category_keys)).order_by(Category.key)
                )
            ).all()
        )

    manufacturers: list[Manufacturer] = []
    if manufacturer_ids:
        manufacturers = list(
            (
                await db.scalars(
                    select(Manufacturer)
                    .where(Manufacturer.id.in_(manufacturer_ids))
                    .order_by(Manufacturer.id)
                )
            ).all()
        )

    attributes_by_category_id: dict[uuid.UUID, list[CategoryAttribute]] = {
        category.id: [] for category in categories
    }
    category_ids = sorted(attributes_by_category_id, key=str)
    if category_ids:
        definitions = (
            await db.scalars(
                select(CategoryAttribute)
                .where(CategoryAttribute.category_id.in_(category_ids))
                .order_by(
                    CategoryAttribute.category_id,
                    CategoryAttribute.sort_order,
                    CategoryAttribute.key,
                )
            )
        ).all()
        for definition in definitions:
            attributes_by_category_id[definition.category_id].append(definition)

    return ItemCreateValidationContext(
        categories_by_key={category.key: category for category in categories},
        manufacturers_by_id={manufacturer.id: manufacturer for manufacturer in manufacturers},
        attributes_by_category_id=attributes_by_category_id,
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


async def list_manufacturers(
    db: AsyncSession,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> ManufacturerPage:
    statement = select(Manufacturer)
    count_statement = select(func.count()).select_from(Manufacturer)

    if query is not None and query.strip() != "":
        normalized_query = normalize_comparison(
            query,
            field="manufacturer_query",
            max_length=255,
        )
        predicate = Manufacturer.normalized_name.contains(
            normalized_query,
            autoescape=True,
        )
        statement = statement.where(predicate)
        count_statement = count_statement.where(predicate)

    total = await db.scalar(count_statement)
    result = await db.scalars(
        statement.order_by(Manufacturer.normalized_name, Manufacturer.id)
        .limit(limit)
        .offset(offset)
    )
    return ManufacturerPage(items=list(result.all()), total=total or 0)


async def list_categories(db: AsyncSession) -> list[Category]:
    result = await db.scalars(select(Category).order_by(Category.sort_order, Category.key))
    return list(result.all())


async def get_category_record(
    db: AsyncSession,
    category_key: str,
) -> CategoryRecord:
    category = await get_category_by_key(db, category_key)
    attributes = await _get_category_attributes(db, category.id)
    return CategoryRecord(category=category, attributes=attributes)


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


async def _prepare_identity(
    db: AsyncSession, payload: ItemCreate
) -> tuple[Category, list[PreparedAttributeValue], str]:
    context = await load_item_create_validation_context(db, [payload])
    prepared = context.prepare_identity(payload)
    return prepared.category, prepared.values, prepared.identity_signature


async def validate_item_create_payload(
    db: AsyncSession,
    payload: ItemCreate,
) -> ValidatedItemDraft:
    """Validate a catalog-shaped draft without creating an Item.

    Procurement proposed lines use this public boundary so their snapshots
    obey exactly the same leaf/category/identity/attribute rules as normal
    catalog creation.
    """
    context = await load_item_create_validation_context(db, [payload])
    return context.validate(payload)


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


def _stored_attribute_value(
    data_type: AttributeDataType,
    *,
    text_value: str | None,
    integer_value: int | None,
    decimal_value: Decimal | None,
    boolean_value: bool | None,
    enum_value: str | None,
) -> str | int | Decimal | bool:
    if data_type == AttributeDataType.TEXT and text_value is not None:
        return text_value
    if data_type == AttributeDataType.INTEGER and integer_value is not None:
        return integer_value
    if data_type == AttributeDataType.DECIMAL and decimal_value is not None:
        return decimal_value
    if data_type == AttributeDataType.BOOLEAN and boolean_value is not None:
        return boolean_value
    if data_type == AttributeDataType.ENUM and enum_value is not None:
        return enum_value
    raise CatalogSchemaError("stored item attribute value does not match metadata")


async def load_attributes_for_items(
    db: AsyncSession,
    item_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, dict[str, str | int | Decimal | bool]]:
    if not item_ids:
        return {}
    rows = (
        await db.execute(
            select(
                ItemAttributeValue.item_id,
                CategoryAttribute.key,
                CategoryAttribute.data_type,
                ItemAttributeValue.text_value,
                ItemAttributeValue.integer_value,
                ItemAttributeValue.decimal_value,
                ItemAttributeValue.boolean_value,
                ItemAttributeValue.enum_value,
            )
            .join(
                CategoryAttribute,
                CategoryAttribute.id == ItemAttributeValue.category_attribute_id,
            )
            .where(ItemAttributeValue.item_id.in_(item_ids))
            .order_by(
                ItemAttributeValue.item_id,
                CategoryAttribute.sort_order,
                CategoryAttribute.key,
            )
        )
    ).tuples()

    values: dict[uuid.UUID, dict[str, str | int | Decimal | bool]] = {
        item_id: {} for item_id in item_ids
    }
    for (
        item_id,
        key,
        data_type,
        text_value,
        integer_value,
        decimal_value,
        boolean_value,
        enum_value,
    ) in rows:
        values[item_id][key] = _stored_attribute_value(
            data_type,
            text_value=text_value,
            integer_value=integer_value,
            decimal_value=decimal_value,
            boolean_value=boolean_value,
            enum_value=enum_value,
        )
    return values


async def get_item_record(
    db: AsyncSession,
    item_id: uuid.UUID,
) -> ItemRecord:
    item = await db.scalar(
        select(Item)
        .where(Item.id == item_id)
        .options(joinedload(Item.category), joinedload(Item.manufacturer))
    )
    if item is None:
        raise CatalogNotFoundError("item not found")
    attributes = await load_attributes_for_items(db, [item.id])
    return ItemRecord(
        item=item,
        category=item.category,
        manufacturer=item.manufacturer,
        attributes=attributes[item.id],
    )


async def list_items(
    db: AsyncSession,
    *,
    category_key: str | None,
    item_status: ItemStatus,
    limit: int,
    offset: int,
) -> ItemPage:
    category_id: uuid.UUID | None = None
    if category_key is not None:
        category_id = (await get_category_by_key(db, category_key)).id

    filters = [Item.status == item_status]
    if category_id is not None:
        filters.append(Item.category_id == category_id)

    total = await db.scalar(select(func.count()).select_from(Item).where(*filters))
    result = await db.scalars(
        select(Item)
        .where(*filters)
        .options(joinedload(Item.category), joinedload(Item.manufacturer))
        .order_by(Item.normalized_name, Item.id)
        .limit(limit)
        .offset(offset)
    )
    items = list(result.unique().all())
    attributes = await load_attributes_for_items(
        db,
        [item.id for item in items],
    )
    return ItemPage(
        items=[
            ItemRecord(
                item=item,
                category=item.category,
                manufacturer=item.manufacturer,
                attributes=attributes[item.id],
            )
            for item in items
        ],
        total=total or 0,
    )


async def check_duplicate_candidates(
    db: AsyncSession, payload: DuplicateCheckRequest
) -> list[DuplicateCandidate]:
    _, _, signature = await _prepare_identity(db, payload)
    statement = (
        select(Item)
        .where(Item.identity_signature == signature)
        .options(joinedload(Item.manufacturer))
    )
    if payload.exclude_item_id:
        statement = statement.where(Item.id != payload.exclude_item_id)
    items = (await db.scalars(statement)).all()
    return [
        DuplicateCandidate(item, item.manufacturer, "exact_equipment_identity") for item in items
    ]
