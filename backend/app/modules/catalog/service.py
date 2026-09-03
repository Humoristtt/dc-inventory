from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

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

MAX_DECIMAL_PRECISION = 30
MAX_DECIMAL_SCALE = 10
MAX_DECIMAL_INTEGRAL_DIGITS = MAX_DECIMAL_PRECISION - MAX_DECIMAL_SCALE
MIN_SAFE_INTEGER = -(2**53 - 1)
MAX_SAFE_INTEGER = 2**53 - 1
SFP_CATEGORY_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")

SFP_SPEED_PROFILE_SCALARS: dict[str, Decimal | None] = {
    "10 Гбит/с": Decimal("10000"),
    "10/25 Гбит/с": Decimal("25000"),
    "100 Гбит/с": Decimal("100000"),
    "16G FC": Decimal("16000"),
    "25 Гбит/с": Decimal("25000"),
    "4/8/16G FC": Decimal("16000"),
    "40 Гбит/с": Decimal("40000"),
    "8/16/32G FC": Decimal("32000"),
}

SFP_REACH_PROFILE_SCALARS: dict[str, Decimal | None] = {
    "MMF: до 35 м\nOM3: до 100 м": Decimal("100"),
    "OM2: до 20 м\nOM3: до 70 м\nOM4: до 100 м": Decimal("100"),
    "OM2: до 35 м\nOM3: до 100 м\nOM4: до 125 м": Decimal("125"),
    (
        "OM3: 30 м без RS-FEC / 70 м с RS-FEC\n"
        "OM4: 40 м без RS-FEC / 100 м с RS-FEC"
    ): Decimal("100"),
    "OM3: до 100 м\nOM4: до 125 м": Decimal("125"),
    "OM3: до 70 м\nOM4: до 100 м": Decimal("100"),
    "до 10 км": Decimal("10000"),
    "до 100 м": Decimal("100"),
    "до 100 м по OM4": Decimal("100"),
    "до 20 км": Decimal("20000"),
    "до 300 м": Decimal("300"),
}

SFP_WAVELENGTH_PROFILE_SCALARS: dict[str, Decimal | None] = {
    "850 нм": Decimal("850"),
    "1310 нм": Decimal("1310"),
    "1271 / 1291 / 1311 / 1331 нм": None,
}


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


def _prepared_numeric_value(
    value: PreparedAttributeValue,
) -> Decimal | None:
    if value.integer_value is not None:
        return Decimal(value.integer_value)
    if value.decimal_value is not None:
        return value.decimal_value
    return None


def _validate_profile_scalar_pair(
    values: Mapping[str, PreparedAttributeValue],
    *,
    profile_key: str,
    scalar_key: str,
    expectations: Mapping[str, Decimal | None],
) -> None:
    profile_value = values.get(profile_key)
    scalar_value = values.get(scalar_key)

    if (
        profile_value is None
        or profile_value.text_value is None
        or scalar_value is None
    ):
        return

    profile = profile_value.text_value
    actual = _prepared_numeric_value(scalar_value)
    if actual is None:
        raise CatalogSchemaError(
            f"attribute {scalar_key} is not numeric"
        )

    if profile not in expectations:
        raise CatalogValidationError(
            "profile_scalar_unverifiable",
            f"cannot validate {scalar_key} against unrecognized {profile_key}",
        )

    expected = expectations[profile]
    if expected is None or actual != expected:
        raise CatalogValidationError(
            "profile_scalar_mismatch",
            f"attribute {scalar_key} contradicts {profile_key}",
        )


def _validate_sfp_profile_scalar_consistency(
    prepared: Sequence[PreparedAttributeValue],
) -> None:
    values = {
        value.attribute.key: value
        for value in prepared
    }

    _validate_profile_scalar_pair(
        values,
        profile_key="speed_profile",
        scalar_key="speed_mbps",
        expectations=SFP_SPEED_PROFILE_SCALARS,
    )
    _validate_profile_scalar_pair(
        values,
        profile_key="reach_profile",
        scalar_key="reach_m",
        expectations=SFP_REACH_PROFILE_SCALARS,
    )
    _validate_profile_scalar_pair(
        values,
        profile_key="wavelength_profile",
        scalar_key="nominal_wavelength_nm",
        expectations=SFP_WAVELENGTH_PROFILE_SCALARS,
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
        raise CatalogSchemaError(
            f"attribute {attribute.key} has invalid {key} metadata"
        )
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise CatalogSchemaError(
            f"attribute {attribute.key} has invalid {key} metadata"
        ) from exc
    if not value.is_finite():
        raise CatalogSchemaError(
            f"attribute {attribute.key} has non-finite {key} metadata"
        )
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
                raw_value
                if isinstance(raw_value, Decimal)
                else Decimal(str(raw_value).strip())
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
            raise CatalogSchemaError(
                f"attribute {attribute.key} has invalid ENUM allowed_values"
            )
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

    if category_id == SFP_CATEGORY_ID:
        _validate_sfp_profile_scalar_consistency(prepared)

    return prepared


async def _get_category(
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


async def _ensure_internal_code_available(
    db: AsyncSession,
    normalized_internal_code: str | None,
    *,
    exclude_item_id: uuid.UUID | None = None,
) -> None:
    if normalized_internal_code is None:
        return
    statement = select(Item.id).where(
        Item.normalized_internal_code == normalized_internal_code
    )
    if exclude_item_id is not None:
        statement = statement.where(Item.id != exclude_item_id)
    if await db.scalar(statement) is not None:
        raise CatalogConflictError("internal code is already used")


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
        select(Manufacturer.id).where(
            Manufacturer.normalized_name == normalized_name
        )
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
        statement
        .order_by(Manufacturer.normalized_name, Manufacturer.id)
        .limit(limit)
        .offset(offset)
    )
    return ManufacturerPage(items=list(result.all()), total=total or 0)


async def list_categories(db: AsyncSession) -> list[Category]:
    result = await db.scalars(
        select(Category).order_by(Category.sort_order, Category.key)
    )
    return list(result.all())


async def get_category_record(
    db: AsyncSession,
    category_key: str,
) -> CategoryRecord:
    category = await _get_category(db, category_key)
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


async def create_item(db: AsyncSession, payload: ItemCreate) -> uuid.UUID:
    category = await _get_category(db, payload.category_key)
    await _get_manufacturer(db, payload.manufacturer_id)
    definitions = await _get_category_attributes(db, category.id)
    prepared_values = validate_attribute_values(
        category.id,
        definitions,
        payload.attributes,
    )

    name = normalize_inline_text(payload.name, field="name", max_length=255)
    model = normalize_optional_inline_text(
        payload.model,
        field="model",
        max_length=255,
    )
    manufacturer_part_number = normalize_optional_inline_text(
        payload.manufacturer_part_number,
        field="manufacturer_part_number",
        max_length=255,
    )
    internal_code = normalize_optional_inline_text(
        payload.internal_code,
        field="internal_code",
        max_length=128,
    )
    normalized_internal_code = (
        normalize_comparison(
            internal_code,
            field="internal_code",
            max_length=128,
        )
        if internal_code is not None
        else None
    )
    await _ensure_internal_code_available(db, normalized_internal_code)

    item_id = uuid.uuid4()
    item = Item(
        id=item_id,
        category_id=category.id,
        manufacturer_id=payload.manufacturer_id,
        name=name,
        normalized_name=normalize_comparison(
            name,
            field="name",
            max_length=255,
        ),
        model=model,
        normalized_model=(
            normalize_comparison(
                model,
                field="model",
                max_length=255,
            )
            if model is not None
            else None
        ),
        manufacturer_part_number=manufacturer_part_number,
        normalized_manufacturer_part_number=(
            normalize_comparison(
                manufacturer_part_number,
                field="manufacturer_part_number",
                max_length=255,
            )
            if manufacturer_part_number is not None
            else None
        ),
        internal_code=internal_code,
        normalized_internal_code=normalized_internal_code,
        description=normalize_optional_text(payload.description),
        accounting_mode=payload.accounting_mode or category.default_accounting_mode,
        status=ItemStatus.ACTIVE,
        comment=normalize_optional_text(payload.comment),
        datasheet_url=payload.datasheet_url,
        technical_data_source=normalize_optional_text(
            payload.technical_data_source
        ),
    )
    db.add(item)
    db.add_all(_item_attribute_rows(item_id, category.id, prepared_values))
    await db.flush()
    return item_id


async def update_item(
    db: AsyncSession,
    item_id: uuid.UUID,
    payload: ItemPatch,
    *,
    fields_set: set[str],
) -> uuid.UUID:
    item = await db.scalar(
        select(Item).where(Item.id == item_id).with_for_update()
    )
    if item is None:
        raise CatalogNotFoundError("item not found")

    if "category_key" in fields_set:
        raise CatalogValidationError(
            "category_immutable",
            "item category cannot be changed",
        )
    if "accounting_mode" in fields_set:
        raise CatalogValidationError(
            "accounting_mode_immutable",
            "item accounting mode cannot be changed",
        )

    if "manufacturer_id" in fields_set:
        await _get_manufacturer(db, payload.manufacturer_id)
        item.manufacturer_id = payload.manufacturer_id
    if "name" in fields_set:
        if payload.name is None:
            raise CatalogValidationError("name_required", "name must not be null")
        item.name = normalize_inline_text(payload.name, field="name", max_length=255)
        item.normalized_name = normalize_comparison(
            item.name,
            field="name",
            max_length=255,
        )
    if "model" in fields_set:
        item.model = normalize_optional_inline_text(
            payload.model,
            field="model",
            max_length=255,
        )
        item.normalized_model = (
            normalize_comparison(
                item.model,
                field="model",
                max_length=255,
            )
            if item.model is not None
            else None
        )
    if "manufacturer_part_number" in fields_set:
        item.manufacturer_part_number = normalize_optional_inline_text(
            payload.manufacturer_part_number,
            field="manufacturer_part_number",
            max_length=255,
        )
        item.normalized_manufacturer_part_number = (
            normalize_comparison(
                item.manufacturer_part_number,
                field="manufacturer_part_number",
                max_length=255,
            )
            if item.manufacturer_part_number is not None
            else None
        )
    if "internal_code" in fields_set:
        item.internal_code = normalize_optional_inline_text(
            payload.internal_code,
            field="internal_code",
            max_length=128,
        )
        item.normalized_internal_code = (
            normalize_comparison(
                item.internal_code,
                field="internal_code",
                max_length=128,
            )
            if item.internal_code is not None
            else None
        )
        await _ensure_internal_code_available(
            db,
            item.normalized_internal_code,
            exclude_item_id=item.id,
        )
    if "description" in fields_set:
        item.description = normalize_optional_text(payload.description)
    if "comment" in fields_set:
        item.comment = normalize_optional_text(payload.comment)
    if "datasheet_url" in fields_set:
        item.datasheet_url = payload.datasheet_url
    if "technical_data_source" in fields_set:
        item.technical_data_source = normalize_optional_text(
            payload.technical_data_source
        )

    if "attributes" in fields_set:
        if payload.attributes is None:
            raise CatalogValidationError(
                "attributes_required",
                "attributes must be an object when supplied",
            )
        definitions = await _get_category_attributes(db, item.category_id)
        prepared_values = validate_attribute_values(
            item.category_id,
            definitions,
            payload.attributes,
        )
        await db.execute(
            delete(ItemAttributeValue).where(ItemAttributeValue.item_id == item.id)
        )
        db.add_all(
            _item_attribute_rows(item.id, item.category_id, prepared_values)
        )

    if fields_set:
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
    item = await db.scalar(
        select(Item).where(Item.id == item_id).with_for_update()
    )
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


async def _load_attributes_for_items(
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
    attributes = await _load_attributes_for_items(db, [item.id])
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
        category_id = (await _get_category(db, category_key)).id

    filters = [Item.status == item_status]
    if category_id is not None:
        filters.append(Item.category_id == category_id)

    total = await db.scalar(
        select(func.count()).select_from(Item).where(*filters)
    )
    result = await db.scalars(
        select(Item)
        .where(*filters)
        .options(joinedload(Item.category), joinedload(Item.manufacturer))
        .order_by(Item.normalized_name, Item.id)
        .limit(limit)
        .offset(offset)
    )
    items = list(result.unique().all())
    attributes = await _load_attributes_for_items(
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
    db: AsyncSession,
    payload: DuplicateCheckRequest,
) -> list[DuplicateCandidate]:
    category = await _get_category(db, payload.category_key)
    await _get_manufacturer(db, payload.manufacturer_id)
    name = normalize_inline_text(payload.name, field="name", max_length=255)
    model = normalize_optional_inline_text(
        payload.model,
        field="model",
        max_length=255,
    )
    manufacturer_part_number = normalize_optional_inline_text(
        payload.manufacturer_part_number,
        field="manufacturer_part_number",
        max_length=255,
    )

    filters = [
        Item.category_id == category.id,
        (
            Item.manufacturer_id.is_(None)
            if payload.manufacturer_id is None
            else Item.manufacturer_id == payload.manufacturer_id
        ),
    ]
    if payload.exclude_item_id is not None:
        filters.append(Item.id != payload.exclude_item_id)

    if manufacturer_part_number is not None:
        filters.append(
            Item.normalized_manufacturer_part_number
            == normalize_comparison(
                manufacturer_part_number,
                field="manufacturer_part_number",
                max_length=255,
            )
        )
        reason = "same_category_manufacturer_mpn"
    else:
        filters.extend(
            [
                Item.normalized_name
                == normalize_comparison(
                    name,
                    field="name",
                    max_length=255,
                ),
                (
                    Item.normalized_model.is_(None)
                    if model is None
                    else Item.normalized_model
                    == normalize_comparison(
                        model,
                        field="model",
                        max_length=255,
                    )
                ),
            ]
        )
        reason = "same_category_manufacturer_name_model"

    result = await db.scalars(
        select(Item)
        .where(*filters)
        .options(joinedload(Item.manufacturer))
        .order_by(Item.created_at, Item.id)
        .limit(20)
    )
    return [
        DuplicateCandidate(
            item=item,
            manufacturer=item.manufacturer,
            reason=reason,
        )
        for item in result.unique().all()
    ]
