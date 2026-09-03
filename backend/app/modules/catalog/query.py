from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sqlalchemy import case, exists, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.modules.catalog.enums import (
    AttributeDataType,
    Availability,
    FilterType,
    ItemSort,
    ItemStatus,
    SortOrder,
)
from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.service import (
    MAX_DECIMAL_INTEGRAL_DIGITS,
    MAX_DECIMAL_SCALE,
    MAX_SAFE_INTEGER,
    MIN_SAFE_INTEGER,
    CatalogSchemaError,
    CatalogValidationError,
    ItemRecord,
    _load_attributes_for_items,
    get_category_record,
    normalize_comparison,
    prepare_attribute_filter_value,
)
from app.modules.inventory.enums import InventoryUnitState
from app.modules.inventory.models import InventoryUnit, Location, StockBalance

type FilterValue = str | int | Decimal | bool
type FacetValue = uuid.UUID | str | int | Decimal | bool
type FacetBound = int | Decimal

DEFAULT_FACET_VALUE_LIMIT = 50
MAX_FACET_VALUE_LIMIT = 100


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
    serial_identity_holder_user_id: uuid.UUID | None
    category_id: uuid.UUID | None
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
    custody_count: int
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


def _parse_controlled_enum(
    raw_value: str,
    enum_type: type[Availability] | type[ItemSort] | type[SortOrder],
    *,
    code: str,
    field: str,
) -> Availability | ItemSort | SortOrder:
    value = raw_value.strip()
    value = value.upper() if enum_type is Availability else value.lower()
    try:
        return enum_type(value)
    except ValueError as error:
        raise CatalogValidationError(code, f"invalid {field}") from error


def _normalize_query_tokens(q: str | None) -> tuple[str, ...]:
    if q is None:
        return ()
    normalized = " ".join(q.split())
    if len(normalized) > 200:
        raise CatalogValidationError("search_too_long", "q exceeds 200 characters")
    if not normalized:
        return ()
    return tuple(normalize_comparison(token) for token in normalized.split(" "))


async def build_catalog_query_spec(
    db: AsyncSession,
    *,
    q: str | None = None,
    serial_identity_holder_user_id: uuid.UUID | None = None,
    category_key: str | None = None,
    item_status: ItemStatus = ItemStatus.ACTIVE,
    manufacturer_ids: Sequence[uuid.UUID] = (),
    availability: str = Availability.ANY.value,
    location_ids: Sequence[uuid.UUID] = (),
    sort: str = ItemSort.NAME.value,
    order: str = SortOrder.ASC.value,
    filter_expressions: Sequence[str] = (),
) -> CatalogQuerySpec:
    category: Category | None = None
    definitions: list[CategoryAttribute] = []
    if category_key is not None:
        category_record = await get_category_record(db, category_key)
        category = category_record.category
        definitions = category_record.attributes
    if filter_expressions and category is None:
        raise CatalogValidationError(
            "filter_category_required",
            "category is required when attribute filters are supplied",
        )

    parsed_availability = cast(
        Availability,
        _parse_controlled_enum(
            availability,
            Availability,
            code="availability_invalid",
            field="availability",
        ),
    )
    parsed_sort = cast(
        ItemSort,
        _parse_controlled_enum(sort, ItemSort, code="sort_invalid", field="sort"),
    )
    parsed_order = cast(
        SortOrder,
        _parse_controlled_enum(order, SortOrder, code="order_invalid", field="order"),
    )

    by_key = {definition.key: definition for definition in definitions}
    parsed_filters: list[AttributeFilter] = []
    range_boundaries: set[tuple[str, str]] = set()
    for expression in filter_expressions:
        parts = expression.split(":", 2)
        if len(parts) != 3 or not parts[0].strip() or not parts[1].strip():
            raise CatalogValidationError(
                "filter_malformed",
                "filter must use <attribute_key>:<operator>:<value>",
            )
        key = parts[0].strip().casefold()
        operator = parts[1].strip().lower()
        raw_value = parts[2]
        attribute = by_key.get(key)
        if attribute is None:
            raise CatalogValidationError(
                "filter_unknown_attribute",
                f"unknown category attribute: {key}",
            )
        if not attribute.filterable or attribute.filter_type == FilterType.NONE:
            raise CatalogValidationError(
                "filter_not_filterable",
                f"attribute {key} is not filterable",
            )

        # Numeric RANGE metadata also accepts exact equality: current schemas use
        # RANGE for engineering values while the public contract supports eq.
        allowed_operators = (
            {"eq"} if attribute.filter_type == FilterType.EXACT else {"eq", "gte", "lte"}
        )
        if operator not in allowed_operators:
            raise CatalogValidationError(
                "filter_operator_not_allowed",
                f"operator {operator} is not allowed for attribute {key}",
            )
        if operator in {"gte", "lte"} and attribute.data_type not in {
            AttributeDataType.INTEGER,
            AttributeDataType.DECIMAL,
        }:
            raise CatalogValidationError(
                "filter_operator_not_allowed",
                f"operator {operator} requires a numeric attribute",
            )
        if operator in {"gte", "lte"}:
            boundary = (key, operator)
            if boundary in range_boundaries:
                raise CatalogValidationError(
                    "filter_range_boundary_conflict",
                    f"duplicate {operator} boundary for attribute {key}",
                )
            range_boundaries.add(boundary)
        try:
            value = prepare_attribute_filter_value(attribute, raw_value)
        except CatalogValidationError as error:
            raise CatalogValidationError(
                "filter_value_invalid",
                str(error),
            ) from error
        parsed_filters.append(
            AttributeFilter(
                attribute_id=attribute.id,
                key=attribute.key,
                data_type=attribute.data_type,
                filter_type=attribute.filter_type,
                operator=operator,
                value=value,
            )
        )

    return CatalogQuerySpec(
        tokens=_normalize_query_tokens(q),
        serial_identity_holder_user_id=serial_identity_holder_user_id,
        category_id=category.id if category is not None else None,
        category_key=category.key if category is not None else None,
        status=item_status,
        manufacturer_ids=tuple(sorted(set(manufacturer_ids), key=str)),
        availability=parsed_availability,
        location_ids=tuple(sorted(set(location_ids), key=str)),
        attribute_filters=tuple(parsed_filters),
        sort=parsed_sort,
        order=parsed_order,
    )


def _inventory_aggregate() -> Subquery:
    quantity = select(
        StockBalance.item_id.label("item_id"),
        func.sum(
            case(
                (StockBalance.location_id.is_not(None), StockBalance.quantity),
                else_=0,
            )
        ).label("available_count"),
        func.sum(
            case(
                (StockBalance.holder_user_id.is_not(None), StockBalance.quantity),
                else_=0,
            )
        ).label("custody_count"),
    ).group_by(StockBalance.item_id)
    serial = (
        select(
            InventoryUnit.item_id.label("item_id"),
            func.count()
            .filter(InventoryUnit.state == InventoryUnitState.STORED)
            .label("available_count"),
            func.count()
            .filter(InventoryUnit.state == InventoryUnitState.ISSUED)
            .label("custody_count"),
        )
        .where(InventoryUnit.state.in_([InventoryUnitState.STORED, InventoryUnitState.ISSUED]))
        .group_by(InventoryUnit.item_id)
    )
    inventory_rows = union_all(quantity, serial).subquery("inventory_rows")
    return (
        select(
            inventory_rows.c.item_id,
            func.sum(inventory_rows.c.available_count).label("available_count"),
            func.sum(inventory_rows.c.custody_count).label("custody_count"),
        )
        .group_by(inventory_rows.c.item_id)
        .subquery("inventory")
    )


def _available(inventory: Subquery) -> ColumnElement[int]:
    return cast(ColumnElement[int], func.coalesce(inventory.c.available_count, 0))


def _custody(inventory: Subquery) -> ColumnElement[int]:
    return cast(ColumnElement[int], func.coalesce(inventory.c.custody_count, 0))


def _total(inventory: Subquery) -> ColumnElement[int]:
    return _available(inventory) + _custody(inventory)


def _escaped_contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _safe_integer_token(token: str) -> int | None:
    if re.fullmatch(r"[+-]?\d+", token) is None:
        return None
    try:
        value = int(token)
    except ValueError:
        return None
    return value if MIN_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER else None


def _safe_decimal_token(token: str) -> Decimal | None:
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    _, digits, exponent = value.as_tuple()
    exponent_value = cast(int, exponent)
    fractional_digits = max(-exponent_value, 0)
    integer_digits = 0 if value.is_zero() else max(len(digits) + exponent_value, 0)
    if fractional_digits > MAX_DECIMAL_SCALE or integer_digits > MAX_DECIMAL_INTEGRAL_DIGITS:
        return None
    return value


def _search_predicate(
    token: str,
    serial_identity_holder_user_id: uuid.UUID | None,
) -> ColumnElement[bool]:
    pattern = _escaped_contains_pattern(token)
    serial_identity_conditions: list[ColumnElement[bool]] = [
        InventoryUnit.item_id == Item.id,
        or_(
            InventoryUnit.normalized_serial_number.like(pattern, escape="\\"),
            InventoryUnit.normalized_wwn.like(pattern, escape="\\"),
        ),
    ]
    if serial_identity_holder_user_id is not None:
        serial_identity_conditions.extend(
            [
                InventoryUnit.state == InventoryUnitState.ISSUED,
                InventoryUnit.current_holder_user_id
                == serial_identity_holder_user_id,
            ]
        )

    common = or_(
        Item.normalized_name.like(pattern, escape="\\"),
        Item.normalized_model.like(pattern, escape="\\"),
        Item.normalized_manufacturer_part_number.like(pattern, escape="\\"),
        Item.normalized_internal_code.like(pattern, escape="\\"),
        exists(
            select(literal(1))
            .where(
                Manufacturer.id == Item.manufacturer_id,
                Manufacturer.normalized_name.like(pattern, escape="\\"),
            )
            .correlate(Item)
        ),
        exists(
            select(literal(1))
            .where(*serial_identity_conditions)
            .correlate(Item)
        ),
    )

    attribute_conditions: list[ColumnElement[bool]] = [
        ItemAttributeValue.text_value.ilike(pattern, escape="\\"),
        ItemAttributeValue.enum_value.ilike(pattern, escape="\\"),
    ]
    integer_value = _safe_integer_token(token)
    if integer_value is not None:
        attribute_conditions.append(ItemAttributeValue.integer_value == integer_value)
    decimal_value = _safe_decimal_token(token)
    if decimal_value is not None:
        attribute_conditions.append(ItemAttributeValue.decimal_value == decimal_value)
    if token in {"true", "false"}:
        attribute_conditions.append(ItemAttributeValue.boolean_value.is_(token == "true"))

    searchable_attribute = exists(
        select(literal(1))
        .select_from(ItemAttributeValue)
        .join(
            CategoryAttribute,
            CategoryAttribute.id == ItemAttributeValue.category_attribute_id,
        )
        .where(
            ItemAttributeValue.item_id == Item.id,
            CategoryAttribute.searchable.is_(True),
            or_(*attribute_conditions),
        )
        .correlate(Item)
    )
    return or_(common, searchable_attribute)


def _attribute_value_column(
    data_type: AttributeDataType,
) -> Any:
    if data_type == AttributeDataType.TEXT:
        return ItemAttributeValue.text_value
    if data_type == AttributeDataType.INTEGER:
        return ItemAttributeValue.integer_value
    if data_type == AttributeDataType.DECIMAL:
        return ItemAttributeValue.decimal_value
    if data_type == AttributeDataType.BOOLEAN:
        return ItemAttributeValue.boolean_value
    if data_type == AttributeDataType.ENUM:
        return ItemAttributeValue.enum_value
    raise CatalogSchemaError("unsupported attribute data type")


def _attribute_filter_predicate(
    filters: Sequence[AttributeFilter],
) -> ColumnElement[bool]:
    first = filters[0]
    column = _attribute_value_column(first.data_type)
    equal_values = [
        attribute_filter.value for attribute_filter in filters if attribute_filter.operator == "eq"
    ]
    conditions: list[ColumnElement[bool]] = [
        ItemAttributeValue.item_id == Item.id,
        ItemAttributeValue.category_attribute_id == first.attribute_id,
    ]
    if equal_values:
        if first.data_type == AttributeDataType.TEXT:
            conditions.append(
                or_(
                    *[
                        ItemAttributeValue.text_value.ilike(
                            str(value)
                            .replace("\\", "\\\\")
                            .replace("%", "\\%")
                            .replace("_", "\\_"),
                            escape="\\",
                        )
                        for value in equal_values
                    ]
                )
            )
        else:
            conditions.append(column.in_(equal_values))
    for attribute_filter in filters:
        if attribute_filter.operator == "gte":
            conditions.append(column >= attribute_filter.value)
        elif attribute_filter.operator == "lte":
            conditions.append(column <= attribute_filter.value)
    return cast(
        ColumnElement[bool],
        exists(select(literal(1)).where(*conditions).correlate(Item)),
    )


def _item_predicates(
    spec: CatalogQuerySpec,
    inventory: Subquery,
    *,
    exclude: frozenset[str] = frozenset(),
) -> list[ColumnElement[bool]]:
    predicates: list[ColumnElement[bool]] = [Item.status == spec.status]
    if spec.category_id is not None and "category" not in exclude:
        predicates.append(Item.category_id == spec.category_id)
    if spec.manufacturer_ids and "manufacturer" not in exclude:
        predicates.append(Item.manufacturer_id.in_(spec.manufacturer_ids))
    if spec.availability != Availability.ANY and "availability" not in exclude:
        if spec.availability == Availability.IN_STOCK:
            predicates.append(_available(inventory) > 0)
        else:
            predicates.append(_available(inventory) == 0)
    if spec.location_ids and "location" not in exclude:
        predicates.append(
            or_(
                exists(
                    select(literal(1))
                    .where(
                        StockBalance.item_id == Item.id,
                        StockBalance.location_id.in_(spec.location_ids),
                        StockBalance.quantity > 0,
                    )
                    .correlate(Item)
                ),
                exists(
                    select(literal(1))
                    .where(
                        InventoryUnit.item_id == Item.id,
                        InventoryUnit.state == InventoryUnitState.STORED,
                        InventoryUnit.current_location_id.in_(spec.location_ids),
                    )
                    .correlate(Item)
                ),
            )
        )
    predicates.extend(
        _search_predicate(
            token,
            spec.serial_identity_holder_user_id,
        )
        for token in spec.tokens
    )

    by_key: dict[str, list[AttributeFilter]] = defaultdict(list)
    for attribute_filter in spec.attribute_filters:
        if f"attribute:{attribute_filter.key}" not in exclude:
            by_key[attribute_filter.key].append(attribute_filter)
    predicates.extend(_attribute_filter_predicate(filters) for filters in by_key.values())
    return predicates


def _matching_items(
    spec: CatalogQuerySpec,
    inventory: Subquery,
    *,
    exclude: frozenset[str] = frozenset(),
) -> Subquery:
    return (
        select(Item.id.label("item_id"))
        .outerjoin(inventory, inventory.c.item_id == Item.id)
        .where(*_item_predicates(spec, inventory, exclude=exclude))
        .subquery("matching_items")
    )


def _ordered_statement(
    statement: Any,
    spec: CatalogQuerySpec,
    inventory: Subquery,
) -> Any:
    descending = spec.order == SortOrder.DESC

    def direction(column: Any) -> Any:
        return column.desc() if descending else column.asc()

    if spec.sort == ItemSort.MANUFACTURER:
        return statement.order_by(
            direction(Manufacturer.normalized_name).nulls_last(),
            direction(Item.normalized_name),
            direction(Item.id),
        )
    if spec.sort == ItemSort.AVAILABLE:
        return statement.order_by(
            direction(_available(inventory)),
            direction(Item.normalized_name),
            direction(Item.id),
        )
    if spec.sort == ItemSort.TOTAL:
        return statement.order_by(
            direction(_total(inventory)),
            direction(Item.normalized_name),
            direction(Item.id),
        )
    return statement.order_by(
        direction(Item.normalized_name),
        direction(Item.id),
    )


async def query_catalog_items(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    *,
    limit: int,
    offset: int,
) -> CatalogItemPage:
    inventory = _inventory_aggregate()
    predicates = _item_predicates(spec, inventory)
    total = await db.scalar(
        select(func.count())
        .select_from(Item)
        .outerjoin(inventory, inventory.c.item_id == Item.id)
        .where(*predicates)
    )
    statement = (
        select(
            Item,
            _available(inventory).label("available_count"),
            _custody(inventory).label("custody_count"),
        )
        .outerjoin(inventory, inventory.c.item_id == Item.id)
        .outerjoin(Manufacturer, Manufacturer.id == Item.manufacturer_id)
        .where(*predicates)
        .options(joinedload(Item.category), joinedload(Item.manufacturer))
    )
    statement = _ordered_statement(statement, spec, inventory).limit(limit).offset(offset)
    rows = (await db.execute(statement)).tuples().all()
    items = [row[0] for row in rows]
    attributes = await _load_attributes_for_items(db, [item.id for item in items])
    records: list[CatalogListRecord] = []
    for item, available_count, custody_count in rows:
        available = int(available_count)
        custody = int(custody_count)
        records.append(
            CatalogListRecord(
                record=ItemRecord(
                    item=item,
                    category=item.category,
                    manufacturer=item.manufacturer,
                    attributes=attributes[item.id],
                ),
                inventory=InventorySummary(
                    available_count=available,
                    custody_count=custody,
                    total_count=available + custody,
                ),
            )
        )
    return CatalogItemPage(items=records, total=int(total or 0))


async def _category_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    inventory: Subquery,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(spec, inventory, exclude=frozenset({"category"}))
    rows = (
        (
            await db.execute(
                select(Category.key, Category.display_name, func.count())
                .select_from(Category)
                .join(Item, Item.category_id == Category.id)
                .join(matching, matching.c.item_id == Item.id)
                .group_by(
                    Category.id,
                    Category.key,
                    Category.display_name,
                    Category.sort_order,
                )
                .order_by(Category.sort_order, Category.key)
                .limit(value_limit + 1)
                .offset(value_offset)
            )
        )
        .tuples()
        .all()
    )
    has_more = len(rows) > value_limit
    rows = rows[:value_limit]
    return FacetRecord(
        key="category",
        label="Категория",
        data_type=AttributeDataType.TEXT,
        unit=None,
        filter_type=FilterType.EXACT,
        values=tuple(
            FacetValueRecord(
                value=key,
                label=label,
                count=int(count),
            )
            for key, label, count in rows
        ),
        values_has_more=has_more,
    )


async def _manufacturer_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    inventory: Subquery,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(spec, inventory, exclude=frozenset({"manufacturer"}))
    rows = (
        (
            await db.execute(
                select(Manufacturer.id, Manufacturer.name, func.count())
                .select_from(Manufacturer)
                .join(Item, Item.manufacturer_id == Manufacturer.id)
                .join(matching, matching.c.item_id == Item.id)
                .group_by(
                    Manufacturer.id,
                    Manufacturer.name,
                    Manufacturer.normalized_name,
                )
                .order_by(Manufacturer.normalized_name, Manufacturer.id)
                .limit(value_limit + 1)
                .offset(value_offset)
            )
        )
        .tuples()
        .all()
    )
    has_more = len(rows) > value_limit
    rows = rows[:value_limit]
    return FacetRecord(
        key="manufacturer",
        label="Производитель",
        data_type=AttributeDataType.TEXT,
        unit=None,
        filter_type=FilterType.EXACT,
        values=tuple(
            FacetValueRecord(
                value=identifier,
                label=name,
                count=int(count),
            )
            for identifier, name, count in rows
        ),
        values_has_more=has_more,
    )


async def _availability_facet(
    db: AsyncSession, spec: CatalogQuerySpec, inventory: Subquery
) -> FacetRecord:
    matching = _matching_items(spec, inventory, exclude=frozenset({"availability"}))
    in_stock = _available(inventory) > 0
    rows = (
        await db.execute(
            select(in_stock.label("in_stock"), func.count())
            .select_from(matching)
            .outerjoin(inventory, inventory.c.item_id == matching.c.item_id)
            .group_by(in_stock)
        )
    ).tuples()
    counts = {bool(value): int(count) for value, count in rows}
    labels = (
        (True, Availability.IN_STOCK, "В наличии"),
        (False, Availability.OUT_OF_STOCK, "Нет в наличии"),
    )
    return FacetRecord(
        key="availability",
        label="Наличие",
        data_type=AttributeDataType.ENUM,
        unit=None,
        filter_type=FilterType.EXACT,
        values=tuple(
            FacetValueRecord(value=machine.value, label=label, count=counts[state])
            for state, machine, label in labels
            if counts.get(state, 0) > 0
        ),
    )


def _location_item_pairs() -> Subquery:
    quantity = select(
        StockBalance.item_id.label("item_id"),
        StockBalance.location_id.label("location_id"),
    ).where(StockBalance.location_id.is_not(None), StockBalance.quantity > 0)
    serial = select(
        InventoryUnit.item_id.label("item_id"),
        InventoryUnit.current_location_id.label("location_id"),
    ).where(
        InventoryUnit.state == InventoryUnitState.STORED,
        InventoryUnit.current_location_id.is_not(None),
    )
    return union_all(quantity, serial).subquery("location_item_pairs")


async def _location_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    inventory: Subquery,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(spec, inventory, exclude=frozenset({"location"}))
    pairs = _location_item_pairs()
    rows = (
        (
            await db.execute(
                select(
                    Location.id,
                    Location.code,
                    Location.name,
                    func.count(func.distinct(pairs.c.item_id)),
                )
                .select_from(Location)
                .join(pairs, pairs.c.location_id == Location.id)
                .join(matching, matching.c.item_id == pairs.c.item_id)
                .group_by(
                    Location.id,
                    Location.code,
                    Location.name,
                    Location.normalized_code,
                )
                .order_by(Location.normalized_code, Location.id)
                .limit(value_limit + 1)
                .offset(value_offset)
            )
        )
        .tuples()
        .all()
    )
    has_more = len(rows) > value_limit
    rows = rows[:value_limit]
    return FacetRecord(
        key="location",
        label="Локация",
        data_type=AttributeDataType.TEXT,
        unit=None,
        filter_type=FilterType.EXACT,
        values=tuple(
            FacetValueRecord(
                value=identifier,
                code=code,
                name=name,
                label=f"{code} — {name}",
                count=int(count),
            )
            for identifier, code, name, count in rows
        ),
        values_has_more=has_more,
    )


async def _exact_attribute_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    inventory: Subquery,
    attribute: CategoryAttribute,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(
        spec,
        inventory,
        exclude=frozenset({f"attribute:{attribute.key}"}),
    )
    column = _attribute_value_column(attribute.data_type)
    has_more = False

    if attribute.data_type == AttributeDataType.TEXT:
        normalized = func.lower(ItemAttributeValue.text_value)
        text_rows = (
            (
                await db.execute(
                    select(
                        normalized,
                        func.min(ItemAttributeValue.text_value),
                        func.count(),
                    )
                    .select_from(ItemAttributeValue)
                    .join(
                        matching,
                        matching.c.item_id == ItemAttributeValue.item_id,
                    )
                    .where(
                        ItemAttributeValue.category_attribute_id
                        == attribute.id
                    )
                    .group_by(normalized)
                    .order_by(normalized)
                    .limit(value_limit + 1)
                    .offset(value_offset)
                )
            )
            .tuples()
            .all()
        )
        has_more = len(text_rows) > value_limit
        text_rows = text_rows[:value_limit]
        values = tuple(
            FacetValueRecord(
                value=display,
                label=display,
                count=int(count),
            )
            for _normalized, display, count in text_rows
        )
    else:
        statement = (
            select(column, func.count())
            .select_from(ItemAttributeValue)
            .join(
                matching,
                matching.c.item_id == ItemAttributeValue.item_id,
            )
            .where(
                ItemAttributeValue.category_attribute_id
                == attribute.id
            )
            .group_by(column)
        )

        if attribute.data_type in {
            AttributeDataType.ENUM,
            AttributeDataType.BOOLEAN,
        }:
            exact_rows = (
                (await db.execute(statement))
                .tuples()
                .all()
            )
        else:
            exact_rows = (
                (
                    await db.execute(
                        statement
                        .order_by(column)
                        .limit(value_limit + 1)
                        .offset(value_offset)
                    )
                )
                .tuples()
                .all()
            )
            has_more = len(exact_rows) > value_limit
            exact_rows = exact_rows[:value_limit]

        by_value = {
            value: int(count)
            for value, count in exact_rows
        }

        if attribute.data_type == AttributeDataType.ENUM:
            allowed_values = attribute.allowed_values
            if not isinstance(allowed_values, list):
                raise CatalogSchemaError(
                    f"attribute {attribute.key} has invalid ENUM allowed_values"
                )
            ordered_values: list[FacetValue] = [
                value
                for value in allowed_values
                if value in by_value
            ]
        elif attribute.data_type == AttributeDataType.BOOLEAN:
            ordered_values = [
                value
                for value in (False, True)
                if value in by_value
            ]
        else:
            ordered_values = sorted(by_value)

        values = tuple(
            FacetValueRecord(
                value=value,
                label=(
                    str(value).lower()
                    if isinstance(value, bool)
                    else str(value)
                ),
                count=by_value[value],
            )
            for value in ordered_values
        )

    return FacetRecord(
        key=attribute.key,
        label=attribute.label,
        data_type=attribute.data_type,
        unit=attribute.unit,
        filter_type=attribute.filter_type,
        values=values,
        values_has_more=has_more,
    )


async def _range_attribute_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    inventory: Subquery,
    attribute: CategoryAttribute,
) -> FacetRecord:
    matching = _matching_items(
        spec,
        inventory,
        exclude=frozenset({f"attribute:{attribute.key}"}),
    )
    column = _attribute_value_column(attribute.data_type)
    row = (
        await db.execute(
            select(func.min(column), func.max(column))
            .select_from(ItemAttributeValue)
            .join(matching, matching.c.item_id == ItemAttributeValue.item_id)
            .where(ItemAttributeValue.category_attribute_id == attribute.id)
        )
    ).one()
    minimum, maximum = row
    return FacetRecord(
        key=attribute.key,
        label=attribute.label,
        data_type=attribute.data_type,
        unit=attribute.unit,
        filter_type=attribute.filter_type,
        minimum=cast(FacetBound | None, minimum),
        maximum=cast(FacetBound | None, maximum),
    )


async def query_catalog_facets(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    *,
    value_limit: int = DEFAULT_FACET_VALUE_LIMIT,
    value_offset: int = 0,
    only_key: str | None = None,
) -> list[FacetRecord]:
    if not 1 <= value_limit <= MAX_FACET_VALUE_LIMIT:
        raise CatalogValidationError(
            "facet_limit_invalid",
            "facet value limit is outside the allowed range",
        )
    if value_offset < 0:
        raise CatalogValidationError(
            "facet_offset_invalid",
            "facet value offset must be non-negative",
        )
    if value_offset > 0 and only_key is None:
        raise CatalogValidationError(
            "facet_key_required",
            "facet key is required for a non-zero facet offset",
        )

    inventory = _inventory_aggregate()
    facets: list[FacetRecord] = []

    def wanted(key: str) -> bool:
        return only_key is None or only_key == key

    if spec.category_id is None and wanted("category"):
        facets.append(
            await _category_facet(
                db,
                spec,
                inventory,
                value_limit=value_limit,
                value_offset=value_offset,
            )
        )

    if wanted("manufacturer"):
        facets.append(
            await _manufacturer_facet(
                db,
                spec,
                inventory,
                value_limit=value_limit,
                value_offset=value_offset,
            )
        )

    if wanted("availability"):
        facets.append(
            await _availability_facet(db, spec, inventory)
        )

    if wanted("location"):
        facets.append(
            await _location_facet(
                db,
                spec,
                inventory,
                value_limit=value_limit,
                value_offset=value_offset,
            )
        )

    if spec.category_id is not None:
        definitions = (
            await db.scalars(
                select(CategoryAttribute)
                .where(
                    CategoryAttribute.category_id == spec.category_id,
                    CategoryAttribute.filterable.is_(True),
                )
                .order_by(
                    CategoryAttribute.sort_order,
                    CategoryAttribute.key,
                )
            )
        ).all()

        for attribute in definitions:
            if not wanted(attribute.key):
                continue

            if attribute.filter_type == FilterType.RANGE:
                facets.append(
                    await _range_attribute_facet(
                        db,
                        spec,
                        inventory,
                        attribute,
                    )
                )
            elif attribute.filter_type == FilterType.EXACT:
                facets.append(
                    await _exact_attribute_facet(
                        db,
                        spec,
                        inventory,
                        attribute,
                        value_limit=value_limit,
                        value_offset=value_offset,
                    )
                )
            else:
                raise CatalogSchemaError(
                    f"filterable attribute {attribute.key} "
                    "has invalid filter type"
                )

    if only_key is not None and not facets:
        raise CatalogValidationError(
            "facet_unknown",
            f"unknown or unavailable facet: {only_key}",
        )

    return facets
