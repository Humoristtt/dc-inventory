from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.catalog.enums import AttributeDataType, ItemStatus
from app.modules.catalog.item_validation import _prepare_identity
from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.records import (
    CategoryRecord,
    DuplicateCandidate,
    ItemPage,
    ItemRecord,
    ManufacturerPage,
)
from app.modules.catalog.schemas import DuplicateCheckRequest
from app.modules.catalog.validation import (
    CatalogNotFoundError,
    CatalogSchemaError,
    _normalize_category_key,
    normalize_comparison,
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
