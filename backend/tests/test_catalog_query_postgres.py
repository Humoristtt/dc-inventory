import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Item
from app.modules.catalog.query import (
    build_catalog_query_spec,
    equipment_scope,
    query_catalog_facets,
    query_catalog_items,
)
from app.modules.catalog.schemas import ItemCreate, ManufacturerCreate
from app.modules.catalog.service import CatalogValidationError, create_item, create_manufacturer
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


async def transceiver(
    db: AsyncSession,
    marker: str,
    reach: str,
    category: str = "transceiver_ethernet",
    speed: str = "10 Гбит/с",
) -> uuid.UUID:
    manufacturer = await create_manufacturer(db, ManufacturerCreate(name=uuid.uuid4().hex))
    return await create_item(
        db,
        ItemCreate(
            category_key=category,
            name=marker,
            manufacturer_id=manufacturer.id,
            model=uuid.uuid4().hex,
            attributes={
                "speed": speed,
                "wavelength": "1310 нм",
                "reach": reach,
                "form_factor": "SFP+",
                "fiber": "SMF",
                "connector": "LC",
            },
        ),
    )


async def test_hierarchy_long_range_and_shared_family_facets(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    marker = uuid.uuid4().hex
    short = await transceiver(db, marker, "до 300 м")
    boundary = await transceiver(db, marker, "до 2 км")
    far = await transceiver(db, marker, "до 10 км", "transceiver_fc")
    spec = await build_catalog_query_spec(db, q=marker, category_key="transceivers")
    page = await query_catalog_items(db, spec, limit=20, offset=0)
    assert {r.record.item.id for r in page.items} == {short, boundary, far}

    ordinary_spec = await build_catalog_query_spec(
        db,
        q=marker,
        category_key="transceiver_ethernet",
    )
    ordinary_page = await query_catalog_items(
        db,
        ordinary_spec,
        limit=20,
        offset=0,
    )
    assert {
        record.record.item.id
        for record in ordinary_page.items
    } == {short}

    scope = await equipment_scope(
        db,
        "transceiver_ethernet",
        False,
    )
    scoped_ids = set(
        (
            await db.scalars(
                select(Item.id).where(
                    *scope,
                    Item.name == marker,
                )
            )
        ).all()
    )
    assert scoped_ids == {short}

    spec = await build_catalog_query_spec(
        db, q=marker, category_key="transceivers", long_range=True
    )
    page = await query_catalog_items(db, spec, limit=20, offset=0)
    assert {r.record.item.id for r in page.items} == {boundary, far}
    facets = {f.key: f for f in await query_catalog_facets(db, spec)}
    assert "speed" not in facets and "connector" not in facets
    assert facets["reach_m"].minimum == 2000 and facets["reach_m"].maximum == 10000
    # Family filter resolves matching metadata for both children.
    spec = await build_catalog_query_spec(
        db, q=marker, category_key="transceivers", filter_expressions=["reach_m:gte:2000"]
    )
    assert (await query_catalog_items(db, spec, limit=20, offset=0)).total == 2


async def test_transceiver_speed_sort_is_numeric(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    marker = uuid.uuid4().hex

    slow = await transceiver(
        db,
        marker,
        "до 300 м",
        speed="1 Гбит/с",
    )
    medium = await transceiver(
        db,
        marker,
        "до 300 м",
        speed="10 Гбит/с",
    )
    fast = await transceiver(
        db,
        marker,
        "до 300 м",
        speed="25 Гбит/с",
    )

    ascending = await build_catalog_query_spec(
        db,
        q=marker,
        category_key="transceiver_ethernet",
        sort="speed",
        order="asc",
    )
    ascending_page = await query_catalog_items(
        db,
        ascending,
        limit=20,
        offset=0,
    )
    assert [
        record.record.item.id
        for record in ascending_page.items
    ] == [
        slow,
        medium,
        fast,
    ]

    descending = await build_catalog_query_spec(
        db,
        q=marker,
        category_key="transceiver_ethernet",
        sort="speed",
        order="desc",
    )
    descending_page = await query_catalog_items(
        db,
        descending,
        limit=20,
        offset=0,
    )
    assert [
        record.record.item.id
        for record in descending_page.items
    ] == [
        fast,
        medium,
        slow,
    ]


async def test_scoped_facets_free_text_and_pagination(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    marker = uuid.uuid4().hex
    ids = []
    for color, length in [("pearlescent", "5"), ("blue", "5"), ("blue", "7")]:
        payload = cable_payload(color=color + marker, length_m=length)
        payload.name = marker
        ids.append(await create_item(db, payload))
    spec = await build_catalog_query_spec(db, q=marker, category_key="optical_patch_cord")
    facets = {f.key: f for f in await query_catalog_facets(db, spec)}
    assert {v.value for v in facets["color"].values} == {"pearlescent" + marker, "blue" + marker}
    assert "fiber" not in facets and "ports" not in facets
    assert facets["length_m"].minimum == 5 and facets["length_m"].maximum == 7
    pages = [await query_catalog_items(db, spec, limit=1, offset=i) for i in range(3)]
    assert all(p.total == 3 for p in pages)
    assert {p.items[0].record.item.id for p in pages} == set(ids)
    spec = await build_catalog_query_spec(
        db,
        q=marker,
        category_key="optical_patch_cord",
        filter_expressions=["color:eq:blue" + marker, "length_m:gte:6"],
    )
    assert [
        r.record.item.id for r in (await query_catalog_items(db, spec, limit=20, offset=0)).items
    ] == [ids[2]]


@pytest.mark.parametrize(
    "expressions",
    [
        ["ports:eq:2"],
        ["color:gte:blue"],
        ["length_m:gte:abc"],
        ["bad"],
        ["length_m:gte:1", "length_m:gte:2"],
    ],
)
async def test_invalid_filters_are_rejected(
    warehouse_db: AsyncSession,
    expressions: list[str],
) -> None:
    with pytest.raises(CatalogValidationError):
        await build_catalog_query_spec(
            warehouse_db, category_key="optical_patch_cord", filter_expressions=expressions
        )


@pytest.mark.parametrize("reach", ["unknown", "до 2 км experimental", "10/20 км"])
async def test_ambiguous_reach_rejected(
    warehouse_db: AsyncSession,
    reach: str,
) -> None:
    with pytest.raises(CatalogValidationError, match="reach"):
        await transceiver(warehouse_db, uuid.uuid4().hex, reach)


@pytest.mark.parametrize(
    ("category_key", "query_count"),
    [(None, 0), ("optical_patch_cord", 2), ("transceivers", 3)],
)
async def test_request_metadata_round_trip_budget(
    warehouse_db: AsyncSession, category_key: str | None, query_count: int
) -> None:
    from tests.sql_capture import capture_sql

    connection = await warehouse_db.connection()
    with capture_sql(connection) as preparation:
        spec = await build_catalog_query_spec(warehouse_db, category_key=category_key)
    assert len(preparation) == query_count
    with capture_sql(connection) as facets:
        await query_catalog_facets(warehouse_db, spec)
    assert not any(sql.startswith("SELECT category_attributes.") for sql in facets)
    assert not any(sql.startswith("SELECT categories.id,") for sql in facets)
    assert not any("sum(stock_balances.quantity)" in sql for sql in facets)


async def test_facets_self_exclude_and_paginate_with_stock(warehouse_db: AsyncSession) -> None:
    from tests.warehouse_helpers import Scenario, move, scenario

    db = warehouse_db
    seed = await scenario(db)
    marker = uuid.uuid4().hex
    items = []
    for color, length in [("amber", "5"), ("blue", "7"), ("cyan", "9")]:
        payload = cable_payload(color=color, length_m=length)
        payload.name = marker
        items.append(await create_item(db, payload))
    for item in items[:2]:
        movement_scenario: Scenario = (seed[0], item, seed[2], seed[3])
        await move(db, movement_scenario, "RECEIPT", 2, destination=seed[2])
        await move(db, movement_scenario, "RECEIPT", 3, destination=seed[3])
    spec = await build_catalog_query_spec(
        db, q=marker, category_key="optical_patch_cord", availability="IN_STOCK"
    )
    availability = (await query_catalog_facets(db, spec, only_key="availability"))[0]
    assert {v.value: v.count for v in availability.values} == {"IN_STOCK": 2, "OUT_OF_STOCK": 1}
    first = (await query_catalog_facets(db, spec, only_key="color", value_limit=1))[0]
    second = (
        await query_catalog_facets(db, spec, only_key="color", value_limit=1, value_offset=1)
    )[0]
    assert [v.value for v in first.values] == ["amber"] and first.values_has_more
    assert [v.value for v in second.values] == ["blue"] and not second.values_has_more
    spec = await build_catalog_query_spec(
        db,
        q=marker,
        category_key="optical_patch_cord",
        location_ids=[seed[2]],
        filter_expressions=["color:eq:blue", "length_m:gte:6"],
    )
    color_facet = (await query_catalog_facets(db, spec, only_key="color"))[0]
    assert [(v.value, v.count) for v in color_facet.values] == [("blue", 1)]
    length_facet = (await query_catalog_facets(db, spec, only_key="length_m"))[0]
    assert length_facet.minimum == length_facet.maximum == 7
    locations = (await query_catalog_facets(db, spec, only_key="location"))[0]
    assert {v.value: v.count for v in locations.values} == {seed[2]: 1, seed[3]: 1}
