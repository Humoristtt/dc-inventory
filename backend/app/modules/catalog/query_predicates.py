from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import exists, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.modules.catalog.enums import AttributeDataType, Availability
from app.modules.catalog.models import (
    CategoryAttribute,
    Item,
    ItemAttributeValue,
)
from app.modules.catalog.query_search import _search_predicate
from app.modules.catalog.query_spec import (
    long_range_predicate,
    rj45_transceiver_predicate,
)
from app.modules.catalog.query_types import (
    AttributeFilter,
    CatalogQuerySpec,
)
from app.modules.catalog.validation import CatalogSchemaError
from app.modules.inventory.models import StockBalance


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
        ItemAttributeValue.category_attribute_id.in_(
            select(CategoryAttribute.id).where(CategoryAttribute.key == first.key)
        ),
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


def _in_stock() -> ColumnElement[bool]:
    # Quantities are nonnegative in PostgreSQL; existence avoids a full stock SUM.
    return exists(
        select(literal(1)).where(StockBalance.item_id == Item.id, StockBalance.quantity > 0)
    ).correlate(Item)


def _item_predicates(
    spec: CatalogQuerySpec,
    *,
    exclude: frozenset[str] = frozenset(),
) -> list[ColumnElement[bool]]:
    predicates: list[ColumnElement[bool]] = [Item.status == spec.status]
    if spec.category_key is not None:
        predicates.append(Item.category_id.in_(spec.category_ids))
    if spec.rj45:
        predicates.append(rj45_transceiver_predicate())
    elif spec.long_range:
        predicates.append(long_range_predicate())
    elif spec.category_key == "transceiver_ethernet":
        predicates.extend(
            [
                ~long_range_predicate(),
                ~rj45_transceiver_predicate(),
            ]
        )
    if spec.manufacturer_ids and "manufacturer" not in exclude:
        predicates.append(Item.manufacturer_id.in_(spec.manufacturer_ids))
    if spec.availability != Availability.ANY and "availability" not in exclude:
        if spec.availability == Availability.IN_STOCK:
            predicates.append(_in_stock())
        else:
            predicates.append(~_in_stock())
    if spec.location_ids and "location" not in exclude:
        predicates.append(
            exists(
                select(literal(1)).where(
                    StockBalance.item_id == Item.id, StockBalance.location_id.in_(spec.location_ids)
                )
            ).correlate(Item)
        )
    predicates.extend(_search_predicate(token) for token in spec.tokens)

    by_key: dict[str, list[AttributeFilter]] = defaultdict(list)
    for attribute_filter in spec.attribute_filters:
        if f"attribute:{attribute_filter.key}" not in exclude:
            by_key[attribute_filter.key].append(attribute_filter)
    predicates.extend(_attribute_filter_predicate(filters) for filters in by_key.values())
    return predicates


def _matching_items(
    spec: CatalogQuerySpec,
    *,
    exclude: frozenset[str] = frozenset(),
) -> Subquery:
    return (
        select(Item.id.label("item_id"))
        .where(*_item_predicates(spec, exclude=exclude))
        .subquery("matching_items")
    )
