from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Numeric, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.modules.catalog.enums import ItemSort, SortOrder
from app.modules.catalog.models import (
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.query_predicates import _item_predicates
from app.modules.catalog.query_search import _search_relevance_score
from app.modules.catalog.query_types import (
    CatalogItemPage,
    CatalogListRecord,
    CatalogQuerySpec,
    InventorySummary,
)
from app.modules.catalog.read_service import load_attributes_for_items
from app.modules.catalog.records import ItemRecord
from app.modules.inventory.models import StockBalance


def _inventory_aggregate() -> Subquery:
    return (
        select(StockBalance.item_id, func.sum(StockBalance.quantity).label("available_count"))
        .group_by(StockBalance.item_id)
        .subquery("inventory")
    )


def _available(inventory: Subquery) -> ColumnElement[int]:
    return cast(ColumnElement[int], func.coalesce(inventory.c.available_count, 0))


def _total(inventory: Subquery) -> ColumnElement[int]:
    return _available(inventory)


def _speed_sort_value() -> Any:
    speed_text = (
        select(ItemAttributeValue.text_value)
        .join(
            CategoryAttribute,
            CategoryAttribute.id == ItemAttributeValue.category_attribute_id,
        )
        .where(
            ItemAttributeValue.item_id == Item.id,
            CategoryAttribute.key == "speed",
        )
        .limit(1)
        .correlate(Item)
        .scalar_subquery()
    )
    numeric_text = func.replace(
        func.substring(
            speed_text,
            r"[0-9]+[.,]?[0-9]*",
        ),
        ",",
        ".",
    )
    return sql_cast(
        numeric_text,
        Numeric(),
    )

def _ordered_statement(
    statement: Any,
    spec: CatalogQuerySpec,
    inventory: Subquery,
) -> Any:
    descending = spec.order == SortOrder.DESC

    def direction(column: Any) -> Any:
        return column.desc() if descending else column.asc()

    if spec.sort == ItemSort.RELEVANCE:
        if not spec.tokens:
            return statement.order_by(
                direction(Item.normalized_name),
                direction(Item.id),
            )

        relevance = _search_relevance_score(
            spec
        )

        return statement.order_by(
            direction(relevance),
            Item.normalized_name.asc(),
            Item.id.asc(),
        )

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
    if spec.sort == ItemSort.SPEED:
        return statement.order_by(
            direction(_speed_sort_value()).nulls_last(),
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
    predicates = _item_predicates(spec)
    total = await db.scalar(select(func.count()).select_from(Item).where(*predicates))
    statement = (
        select(
            Item,
            _available(inventory).label("available_count"),
        )
        .outerjoin(inventory, inventory.c.item_id == Item.id)
        .outerjoin(Manufacturer, Manufacturer.id == Item.manufacturer_id)
        .where(*predicates)
        .options(joinedload(Item.category), joinedload(Item.manufacturer))
    )
    statement = _ordered_statement(statement, spec, inventory).limit(limit).offset(offset)
    rows = (await db.execute(statement)).tuples().all()
    items = [row[0] for row in rows]
    attributes = await load_attributes_for_items(db, [item.id for item in items])
    records: list[CatalogListRecord] = []
    for item, available_count in rows:
        available = int(available_count)
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
                    total_count=available,
                ),
            )
        )
    return CatalogItemPage(items=records, total=int(total or 0))
