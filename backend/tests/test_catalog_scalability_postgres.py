import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.query import (
    build_catalog_query_spec,
    query_catalog_facets,
    query_catalog_items,
)
from app.modules.catalog.service import create_item
from tests.sql_capture import capture_sql
from tests.warehouse_helpers import cable_payload, move, scenario

pytestmark = pytest.mark.asyncio

MAX_FULL_FACET_SELECTS = 10


async def test_cp06_catalog_list_stock_and_facet_scalability(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    marker = uuid.uuid4().hex
    seed = await scenario(db)
    groups: dict[int, list[uuid.UUID]] = {}

    for size in (1, 100, 500):
        group: list[uuid.UUID] = []

        for index in range(size):
            payload = cable_payload(
                color=f"cp06-{marker}-{size}-{index:04d}",
            )
            payload.name = f"CP06-{marker}-GROUP-{size}-END"
            group.append(await create_item(db, payload))

        groups[size] = group

    assert all(len(set(groups[size])) == size for size in groups)

    # Four stocked items; the other 496 in this group have no stock.
    for item_id in groups[500][:4]:
        movement_scenario = (seed[0], item_id, seed[2], seed[3])
        await move(
            db,
            movement_scenario,
            "RECEIPT",
            2,
            destination=seed[2],
        )

    connection = await db.connection()
    list_counts: dict[int, int] = {}
    facet_counts: dict[int, int] = {}

    for size in (1, 100, 500):
        spec = await build_catalog_query_spec(
            db,
            q=f"CP06-{marker}-GROUP-{size}-END",
            category_key="optical_patch_cord",
        )

        with capture_sql(connection) as statements:
            page = await query_catalog_items(
                db,
                spec,
                limit=50,
                offset=0,
            )

        list_counts[size] = len(statements)

        assert page.total == size
        assert len(page.items) == min(50, size)

        with capture_sql(connection) as statements:
            facets = await query_catalog_facets(db, spec)

        facet_counts[size] = len(statements)

        assert isinstance(facets, list)

        if size == 500:
            color = next(facet for facet in facets if facet.key == "color")
            assert len(color.values) == 50
            assert color.values_has_more

            availability = next(facet for facet in facets if facet.key == "availability")
            assert {value.value: value.count for value in availability.values} == {
                "IN_STOCK": 4,
                "OUT_OF_STOCK": 496,
            }

    spec = await build_catalog_query_spec(
        db,
        q=f"CP06-{marker}-GROUP-500-END",
        category_key="optical_patch_cord",
    )

    first = await query_catalog_items(
        db,
        spec,
        limit=50,
        offset=0,
    )
    second = await query_catalog_items(
        db,
        spec,
        limit=50,
        offset=50,
    )
    combined = await query_catalog_items(
        db,
        spec,
        limit=100,
        offset=0,
    )

    first_ids = [entry.record.item.id for entry in first.items]
    second_ids = [entry.record.item.id for entry in second.items]

    assert first.total == second.total == combined.total == 500
    assert len(first_ids) == len(second_ids) == 50
    assert not set(first_ids).intersection(second_ids)
    assert first_ids + second_ids == [entry.record.item.id for entry in combined.items]

    stock_spec = await build_catalog_query_spec(
        db,
        q=f"CP06-{marker}-GROUP-500-END",
        category_key="optical_patch_cord",
        availability="IN_STOCK",
    )
    stocked = await query_catalog_items(
        db,
        stock_spec,
        limit=50,
        offset=0,
    )

    assert stocked.total == 4
    assert {entry.record.item.id for entry in stocked.items} == set(groups[500][:4])
    assert all(entry.inventory.available_count == 2 for entry in stocked.items)

    color_page = (
        await query_catalog_facets(
            db,
            spec,
            only_key="color",
            value_limit=50,
            value_offset=50,
        )
    )[0]

    assert color_page.key == "color"
    assert len(color_page.values) == 50
    assert color_page.values_has_more

    with capture_sql(connection) as scoped_statements:
        scoped_facets = await query_catalog_facets(
            db,
            spec,
            only_key="availability",
        )

    assert len(scoped_statements) == 1
    assert len(scoped_facets) == 1
    assert scoped_facets[0].key == "availability"

    print(
        f"CP06_CATALOG_LIST_SELECTS={list_counts}",
        flush=True,
    )
    print(
        f"CP06_CATALOG_FULL_FACET_SELECTS={facet_counts}",
        flush=True,
    )

    assert list_counts[100] <= list_counts[1] + 1
    assert list_counts[500] <= list_counts[1] + 1

    # Fixed budget for this schema: three base facets and seven attributes.
    assert facet_counts[500] <= MAX_FULL_FACET_SELECTS, (
        f"Full Catalog facets require {facet_counts[500]} SQL "
        f"statements; budget={MAX_FULL_FACET_SELECTS}. "
        f"Counts={facet_counts}"
    )
