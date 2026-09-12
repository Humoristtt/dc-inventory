from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

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
from app.modules.inventory.models import (
    MovementLine,
    StockBalance,
    UserItemCustodyBalance,
)

MAX_DECIMAL_PRECISION = 30
MAX_DECIMAL_SCALE = 10
MAX_DECIMAL_INTEGRAL_DIGITS = MAX_DECIMAL_PRECISION - MAX_DECIMAL_SCALE
MIN_SAFE_INTEGER = -(2**53 - 1)
MAX_SAFE_INTEGER = 2**53 - 1


class CatalogError(RuntimeError):
    code = "catalog_error"


class CatalogValidationError(CatalogError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CatalogNotFoundError(CatalogError):
    code = "catalog_not_found"


class CatalogConflictError(CatalogError):
    code = "catalog_conflict"


class CatalogItemInUseError(CatalogConflictError):
    code = "catalog_item_in_use"


class CatalogSchemaError(CatalogError):
    code = "catalog_schema_invalid"


@dataclass(frozen=True, slots=True)
class PreparedAttributeValue:
    attribute: CategoryAttribute
    text_value: str | None = None
    integer_value: int | None = None
    decimal_value: Decimal | None = None
    boolean_value: bool | None = None
    enum_value: str | None = None


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


def normalize_inline_text(value: str, *, field: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise CatalogValidationError(
            f"{field}_required",
            f"{field} must not be blank",
        )
    if len(normalized) > max_length:
        raise CatalogValidationError(
            f"{field}_too_long",
            f"{field} exceeds {max_length} characters",
        )
    return normalized


def normalize_optional_inline_text(
    value: str | None,
    *,
    field: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise CatalogValidationError(
            f"{field}_too_long",
            f"{field} exceeds {max_length} characters",
        )
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_comparison(
    value: str,
    *,
    field: str | None = None,
    max_length: int | None = None,
) -> str:
    normalized = " ".join(value.split()).casefold()
    if max_length is not None and len(normalized) > max_length:
        error_field = field or "normalized_value"
        raise CatalogValidationError(
            f"{error_field}_too_long",
            f"{error_field} normalized value exceeds {max_length} characters",
        )
    return normalized


def _normalize_category_key(value: str) -> str:
    return normalize_inline_text(value, field="category_key", max_length=64).casefold()


def _numeric_metadata(
    attribute: CategoryAttribute,
    key: str,
) -> Decimal | None:
    metadata = attribute.validation_metadata
    if metadata is None or key not in metadata:
        return None
    raw = metadata[key]
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        raise CatalogSchemaError(f"attribute {attribute.key} has invalid {key} metadata")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise CatalogSchemaError(f"attribute {attribute.key} has invalid {key} metadata") from exc
    if not value.is_finite():
        raise CatalogSchemaError(f"attribute {attribute.key} has non-finite {key} metadata")
    return value


def _validate_numeric_bounds(
    attribute: CategoryAttribute,
    value: Decimal,
) -> None:
    minimum = _numeric_metadata(attribute, "min")
    maximum = _numeric_metadata(attribute, "max")
    if minimum is not None and value < minimum:
        raise CatalogValidationError(
            "attribute_below_minimum",
            f"attribute {attribute.key} must be at least {minimum}",
        )
    if maximum is not None and value > maximum:
        raise CatalogValidationError(
            "attribute_above_maximum",
            f"attribute {attribute.key} must be at most {maximum}",
        )


def _validate_decimal_storage(attribute: CategoryAttribute, value: Decimal) -> None:
    _, digits, exponent = value.as_tuple()
    exponent = cast(int, exponent)
    fractional_digits = max(-exponent, 0)
    integer_digits = 0 if value.is_zero() else max(len(digits) + exponent, 0)
    if fractional_digits > MAX_DECIMAL_SCALE:
        raise CatalogValidationError(
            "decimal_scale_exceeded",
            f"attribute {attribute.key} supports at most {MAX_DECIMAL_SCALE} decimal places",
        )
    if integer_digits > MAX_DECIMAL_INTEGRAL_DIGITS:
        raise CatalogValidationError(
            "decimal_precision_exceeded",
            f"attribute {attribute.key} supports at most "
            f"{MAX_DECIMAL_INTEGRAL_DIGITS} integral digits",
        )


def _prepare_attribute_value(
    attribute: CategoryAttribute,
    raw_value: object,
) -> PreparedAttributeValue | None:
    if attribute.data_type == AttributeDataType.TEXT:
        if not isinstance(raw_value, str):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires TEXT",
            )
        metadata = attribute.validation_metadata or {}
        preserve_whitespace = metadata.get("preserve_whitespace", False)
        if not isinstance(preserve_whitespace, bool):
            raise CatalogSchemaError(
                f"attribute {attribute.key} has invalid preserve_whitespace metadata"
            )
        value = raw_value.strip() if preserve_whitespace else " ".join(raw_value.split())
        if not value:
            if attribute.required:
                raise CatalogValidationError(
                    "required_attribute_missing",
                    f"required attribute {attribute.key} must not be blank",
                )
            return None
        max_length = metadata.get("max_length")
        if max_length is not None:
            if isinstance(max_length, bool) or not isinstance(max_length, int):
                raise CatalogSchemaError(
                    f"attribute {attribute.key} has invalid max_length metadata"
                )
            if len(value) > max_length:
                raise CatalogValidationError(
                    "attribute_too_long",
                    f"attribute {attribute.key} exceeds {max_length} characters",
                )
        return PreparedAttributeValue(attribute=attribute, text_value=value)

    if attribute.data_type == AttributeDataType.INTEGER:
        if type(raw_value) is not int:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires INTEGER",
            )
        integer_value = raw_value
        if not MIN_SAFE_INTEGER <= integer_value <= MAX_SAFE_INTEGER:
            raise CatalogValidationError(
                "integer_out_of_range",
                f"attribute {attribute.key} is outside the exact JSON integer range",
            )
        _validate_numeric_bounds(attribute, Decimal(integer_value))
        return PreparedAttributeValue(
            attribute=attribute,
            integer_value=integer_value,
        )

    if attribute.data_type == AttributeDataType.DECIMAL:
        if isinstance(raw_value, (bool, float)):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires an exact decimal string or integer",
            )
        if not isinstance(raw_value, (Decimal, int, str)):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires DECIMAL",
            )
        if isinstance(raw_value, str) and not raw_value.strip():
            if attribute.required:
                raise CatalogValidationError(
                    "required_attribute_missing",
                    f"required attribute {attribute.key} must not be blank",
                )
            return None
        try:
            decimal_value = (
                raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value).strip())
            )
        except InvalidOperation as exc:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires DECIMAL",
            ) from exc
        if not decimal_value.is_finite():
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires a finite DECIMAL",
            )
        _validate_decimal_storage(attribute, decimal_value)
        _validate_numeric_bounds(attribute, decimal_value)
        return PreparedAttributeValue(
            attribute=attribute,
            decimal_value=decimal_value,
        )

    if attribute.data_type == AttributeDataType.BOOLEAN:
        if type(raw_value) is not bool:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires BOOLEAN",
            )
        return PreparedAttributeValue(
            attribute=attribute,
            boolean_value=raw_value,
        )

    if attribute.data_type == AttributeDataType.ENUM:
        if not isinstance(raw_value, str):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires ENUM",
            )
        enum_value = " ".join(raw_value.split())
        if not enum_value:
            if attribute.required:
                raise CatalogValidationError(
                    "required_attribute_missing",
                    f"required attribute {attribute.key} must not be blank",
                )
            return None
        allowed_values = attribute.allowed_values
        if (
            not isinstance(allowed_values, list)
            or not allowed_values
            or any(not isinstance(value, str) for value in allowed_values)
        ):
            raise CatalogSchemaError(f"attribute {attribute.key} has invalid ENUM allowed_values")
        if enum_value not in allowed_values:
            raise CatalogValidationError(
                "attribute_enum_invalid",
                f"attribute {attribute.key} must be one of its allowed values",
            )
        return PreparedAttributeValue(
            attribute=attribute,
            enum_value=enum_value,
        )

    raise CatalogSchemaError(f"attribute {attribute.key} has unsupported data type")


def prepare_attribute_filter_value(
    attribute: CategoryAttribute,
    raw_value: str,
) -> str | int | Decimal | bool:
    """Parse one query-string value through the canonical attribute validator."""
    candidate: object
    if attribute.data_type == AttributeDataType.INTEGER:
        stripped = raw_value.strip()
        if re.fullmatch(r"[+-]?\d+", stripped) is None:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires INTEGER",
            )
        try:
            candidate = int(stripped)
        except ValueError as error:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires INTEGER",
            ) from error
    elif attribute.data_type == AttributeDataType.BOOLEAN:
        normalized = raw_value.strip().casefold()
        if normalized not in {"true", "false"}:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires true or false",
            )
        candidate = normalized == "true"
    else:
        candidate = raw_value

    prepared = _prepare_attribute_value(attribute, candidate)
    if prepared is None:
        raise CatalogValidationError(
            "attribute_type_mismatch",
            f"attribute {attribute.key} requires a value",
        )
    if attribute.data_type == AttributeDataType.TEXT:
        assert prepared.text_value is not None
        return prepared.text_value
    if attribute.data_type == AttributeDataType.INTEGER:
        assert prepared.integer_value is not None
        return prepared.integer_value
    if attribute.data_type == AttributeDataType.DECIMAL:
        assert prepared.decimal_value is not None
        return prepared.decimal_value
    if attribute.data_type == AttributeDataType.BOOLEAN:
        assert prepared.boolean_value is not None
        return prepared.boolean_value
    if attribute.data_type == AttributeDataType.ENUM:
        assert prepared.enum_value is not None
        return prepared.enum_value
    raise CatalogSchemaError(f"attribute {attribute.key} has unsupported data type")


def validate_attribute_values(
    category_id: uuid.UUID,
    definitions: Sequence[CategoryAttribute],
    supplied_values: Mapping[str, object],
) -> list[PreparedAttributeValue]:
    for attribute in definitions:
        if attribute.category_id != category_id:
            raise CatalogValidationError(
                "cross_category_attribute",
                f"attribute {attribute.key} belongs to another category",
            )

    by_key = {attribute.key: attribute for attribute in definitions}
    unknown_keys = sorted(set(supplied_values) - set(by_key))
    if unknown_keys:
        raise CatalogValidationError(
            "unknown_attribute",
            f"unknown category attributes: {', '.join(unknown_keys)}",
        )

    missing_required = sorted(
        attribute.key
        for attribute in definitions
        if attribute.required and attribute.key not in supplied_values
    )
    if missing_required:
        raise CatalogValidationError(
            "required_attribute_missing",
            f"missing required attributes: {', '.join(missing_required)}",
        )

    prepared: list[PreparedAttributeValue] = []
    for key, raw_value in supplied_values.items():
        value = _prepare_attribute_value(by_key[key], raw_value)
        if value is not None:
            prepared.append(value)

    return prepared


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
    from app.modules.catalog.configuration import LEAVES, MANUFACTURED_LEAVES
    from app.modules.catalog.normalization import item_signature, normalize_reach

    category = await get_category_by_key(db, payload.category_key)
    if category.parent_id is None or category.key not in LEAVES:
        raise CatalogValidationError(
            "leaf_category_required", "items require a fixed leaf category"
        )
    manufacturer = await _get_manufacturer(db, payload.manufacturer_id)
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
    definitions = await _get_category_attributes(db, category.id)
    values = validate_attribute_values(category.id, definitions, attributes)
    normalized = {
        v.attribute.key: next(
            x
            for x in (v.text_value, v.integer_value, v.decimal_value, v.boolean_value, v.enum_value)
            if x is not None
        )
        for v in values
    }
    signature = item_signature(
        category.key, manufacturer.name if manufacturer else None, payload.model, normalized
    )
    return category, values, signature


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
            if payload.model else None
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
    item = await db.scalar(
        select(Item)
        .where(Item.id == item_id)
        .with_for_update()
    )
    if item is None:
        raise CatalogNotFoundError("item not found")

    movement_line_id = await db.scalar(
        select(MovementLine.id)
        .where(MovementLine.item_id == item_id)
        .limit(1)
    )
    if movement_line_id is not None:
        raise CatalogItemInUseError(
            "item has warehouse history and cannot be deleted"
        )

    stock_balance_id = await db.scalar(
        select(StockBalance.id)
        .where(StockBalance.item_id == item_id)
        .limit(1)
    )
    if stock_balance_id is not None:
        raise CatalogItemInUseError(
            "item has warehouse stock state and cannot be deleted"
        )

    custody_balance_id = await db.scalar(
        select(UserItemCustodyBalance.id)
        .where(UserItemCustodyBalance.item_id == item_id)
        .limit(1)
    )
    if custody_balance_id is not None:
        raise CatalogItemInUseError(
            "item has custody state and cannot be deleted"
        )

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
