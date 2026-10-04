from __future__ import annotations

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Subquery

from app.modules.catalog.enums import (
    AttributeDataType,
    Availability,
    FilterType,
)
from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.query_predicates import (
    _attribute_value_column,
    _in_stock,
    _matching_items,
)
from app.modules.catalog.query_types import (
    DEFAULT_FACET_VALUE_LIMIT,
    MAX_FACET_VALUE_LIMIT,
    CatalogQuerySpec,
    FacetBound,
    FacetRecord,
    FacetValue,
    FacetValueRecord,
)
from app.modules.catalog.validation import (
    CatalogSchemaError,
    CatalogValidationError,
)
from app.modules.inventory.models import Location, StockBalance


async def _category_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(spec, exclude=frozenset({"category"}))
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
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(spec, exclude=frozenset({"manufacturer"}))
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


async def _availability_facet(db: AsyncSession, spec: CatalogQuerySpec) -> FacetRecord:
    matching = _matching_items(spec, exclude=frozenset({"availability"}))
    in_stock = _in_stock()
    rows = (
        await db.execute(
            select(in_stock.label("in_stock"), func.count())
            .select_from(Item)
            .join(matching, matching.c.item_id == Item.id)
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
    return select(StockBalance.item_id, StockBalance.location_id).subquery("location_item_pairs")


async def _location_facet(
    db: AsyncSession,
    spec: CatalogQuerySpec,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(spec, exclude=frozenset({"location"}))
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
    attribute: CategoryAttribute,
    *,
    value_limit: int,
    value_offset: int,
) -> FacetRecord:
    matching = _matching_items(
        spec,
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
                        ItemAttributeValue.category_attribute_id.in_(
                            select(CategoryAttribute.id).where(
                                CategoryAttribute.key == attribute.key
                            )
                        )
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
                ItemAttributeValue.category_attribute_id.in_(
                    select(CategoryAttribute.id).where(CategoryAttribute.key == attribute.key)
                )
            )
            .group_by(column)
        )

        if attribute.data_type in {
            AttributeDataType.ENUM,
            AttributeDataType.BOOLEAN,
        }:
            exact_rows = (await db.execute(statement)).tuples().all()
        else:
            exact_rows = (
                (
                    await db.execute(
                        statement.order_by(column).limit(value_limit + 1).offset(value_offset)
                    )
                )
                .tuples()
                .all()
            )
            has_more = len(exact_rows) > value_limit
            exact_rows = exact_rows[:value_limit]

        by_value = {value: int(count) for value, count in exact_rows}

        if attribute.data_type == AttributeDataType.ENUM:
            allowed_values = attribute.allowed_values
            if not isinstance(allowed_values, list):
                raise CatalogSchemaError(
                    f"attribute {attribute.key} has invalid ENUM allowed_values"
                )
            ordered_values: list[FacetValue] = [
                value for value in allowed_values if value in by_value
            ]
        elif attribute.data_type == AttributeDataType.BOOLEAN:
            ordered_values = [value for value in (False, True) if value in by_value]
        else:
            ordered_values = sorted(by_value)

        values = tuple(
            FacetValueRecord(
                value=value,
                label=(str(value).lower() if isinstance(value, bool) else str(value)),
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
    attribute: CategoryAttribute,
) -> FacetRecord:
    matching = _matching_items(
        spec,
        exclude=frozenset({f"attribute:{attribute.key}"}),
    )
    column = _attribute_value_column(attribute.data_type)
    row = (
        await db.execute(
            select(func.min(column), func.max(column))
            .select_from(ItemAttributeValue)
            .join(matching, matching.c.item_id == ItemAttributeValue.item_id)
            .where(
                ItemAttributeValue.category_attribute_id.in_(
                    select(CategoryAttribute.id).where(CategoryAttribute.key == attribute.key)
                )
            )
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

    facets: list[FacetRecord] = []

    def wanted(key: str) -> bool:
        return only_key is None or only_key == key

    if spec.category_id is None and wanted("category"):
        facets.append(
            await _category_facet(
                db,
                spec,
                value_limit=value_limit,
                value_offset=value_offset,
            )
        )

    if wanted("manufacturer"):
        facets.append(
            await _manufacturer_facet(
                db,
                spec,
                value_limit=value_limit,
                value_offset=value_offset,
            )
        )

    if wanted("availability"):
        facets.append(await _availability_facet(db, spec))

    if wanted("location"):
        facets.append(
            await _location_facet(
                db,
                spec,
                value_limit=value_limit,
                value_offset=value_offset,
            )
        )

    if spec.category_id is not None:
        definitions = sorted(
            (attribute for attribute in spec.definitions if attribute.filterable),
            key=lambda attribute: (attribute.sort_order, attribute.key),
        )

        seen: set[str] = set()
        for attribute in definitions:
            if attribute.key in seen:
                continue
            seen.add(attribute.key)
            if not wanted(attribute.key):
                continue

            if attribute.filter_type == FilterType.RANGE:
                facets.append(
                    await _range_attribute_facet(
                        db,
                        spec,
                        attribute,
                    )
                )
            elif attribute.filter_type == FilterType.EXACT:
                facets.append(
                    await _exact_attribute_facet(
                        db,
                        spec,
                        attribute,
                        value_limit=value_limit,
                        value_offset=value_offset,
                    )
                )
            else:
                raise CatalogSchemaError(
                    f"filterable attribute {attribute.key} has invalid filter type"
                )

    if only_key is not None and not facets:
        raise CatalogValidationError(
            "facet_unknown",
            f"unknown or unavailable facet: {only_key}",
        )

    return [
        facet
        for facet in facets
        if only_key is not None
        or facet.values_has_more
        or len(facet.values) > 1
        or (facet.minimum is not None and facet.maximum != facet.minimum)
    ]
