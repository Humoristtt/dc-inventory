from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

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
)
from app.modules.catalog.query_types import (
    MAX_FILTER_EXPRESSION_LENGTH,
    MAX_QUERY_VALUES,
    MAX_SEARCH_TOKENS,
    AttributeFilter,
    CatalogQuerySpec,
)
from app.modules.catalog.service import get_category_by_key
from app.modules.catalog.validation import (
    CatalogValidationError,
    normalize_comparison,
    prepare_attribute_filter_value,
)


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
    tokens = tuple(dict.fromkeys(normalize_comparison(token) for token in normalized.split()))
    if len(tokens) > MAX_SEARCH_TOKENS:
        raise CatalogValidationError("search_too_complex", "q exceeds 12 distinct tokens")
    return tokens


async def build_catalog_query_spec(
    db: AsyncSession,
    *,
    q: str | None = None,
    category_key: str | None = None,
    long_range: bool = False,
    rj45: bool = False,
    item_status: ItemStatus = ItemStatus.ACTIVE,
    manufacturer_ids: Sequence[uuid.UUID] = (),
    availability: str = Availability.ANY.value,
    location_ids: Sequence[uuid.UUID] = (),
    sort: str = ItemSort.NAME.value,
    order: str = SortOrder.ASC.value,
    filter_expressions: Sequence[str] = (),
) -> CatalogQuerySpec:
    tokens = _normalize_query_tokens(q)
    if rj45 and long_range:
        raise CatalogValidationError(
            "transceiver_view_conflict",
            "rj45 and long_range cannot be combined",
        )
    if rj45 and category_key != "transceiver_ethernet":
        raise CatalogValidationError(
            "rj45_category_invalid",
            "rj45 view requires transceiver_ethernet category",
        )
    for field, values in (
        ("manufacturer_ids", manufacturer_ids),
        ("location_ids", location_ids),
        ("filter_expressions", filter_expressions),
    ):
        if len(values) > MAX_QUERY_VALUES:
            raise CatalogValidationError("query_too_complex", f"{field} exceeds 50 values")
    if any(len(expression) > MAX_FILTER_EXPRESSION_LENGTH for expression in filter_expressions):
        raise CatalogValidationError("filter_too_long", "filter exceeds 2048 characters")
    category: Category | None = None
    definitions: list[CategoryAttribute] = []
    category_ids: tuple[uuid.UUID, ...] = ()
    if category_key is not None:
        category = await get_category_by_key(db, category_key)
        category_ids = await scope_category_ids(db, category)
        definitions = list(
            (
                await db.scalars(
                    select(CategoryAttribute)
                    .where(CategoryAttribute.category_id.in_(category_ids))
                    .order_by(CategoryAttribute.key)
                )
            ).all()
        )
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
        tokens=tokens,
        category_ids=category_ids,
        definitions=tuple(definitions),
        long_range=long_range,
        rj45=rj45,
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


async def scope_category_ids(db: AsyncSession, category: Category) -> tuple[uuid.UUID, ...]:
    if category.parent_id is not None:
        return (category.id,)
    return tuple(
        (await db.scalars(select(Category.id).where(Category.parent_id == category.id))).all()
    )


def long_range_predicate() -> ColumnElement[bool]:
    return Item.id.in_(
        select(ItemAttributeValue.item_id)
        .join(CategoryAttribute, CategoryAttribute.id == ItemAttributeValue.category_attribute_id)
        .join(Category, Category.id == CategoryAttribute.category_id)
        .where(
            Category.key == "transceiver_ethernet",
            CategoryAttribute.key == "reach_m",
            ItemAttributeValue.integer_value >= 2000,
        )
    )


def rj45_transceiver_predicate() -> ColumnElement[bool]:
    normalized_connector = func.regexp_replace(
        func.lower(
            ItemAttributeValue.text_value,
        ),
        r"[^a-z0-9]+",
        "",
        "g",
    )
    return Item.id.in_(
        select(ItemAttributeValue.item_id)
        .join(
            CategoryAttribute,
            CategoryAttribute.id == ItemAttributeValue.category_attribute_id,
        )
        .join(
            Category,
            Category.id == CategoryAttribute.category_id,
        )
        .where(
            Category.key == "transceiver_ethernet",
            CategoryAttribute.key == "connector",
            normalized_connector.like("rj45%"),
        )
    )


async def equipment_scope(
    db: AsyncSession,
    key: str | None,
    long_range: bool,
    rj45: bool = False,
) -> list[ColumnElement[bool]]:
    ids = (
        await scope_category_ids(
            db,
            await get_category_by_key(db, key),
        )
        if key is not None
        else ()
    )
    predicates: list[ColumnElement[bool]] = [Item.category_id.in_(ids)] if key else []
    if rj45:
        predicates.append(rj45_transceiver_predicate())
    elif long_range:
        predicates.append(long_range_predicate())
    elif key == "transceiver_ethernet":
        predicates.extend(
            [
                ~long_range_predicate(),
                ~rj45_transceiver_predicate(),
            ]
        )
    return predicates
