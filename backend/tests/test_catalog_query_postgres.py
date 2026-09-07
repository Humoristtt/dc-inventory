import uuid

import pytest

from app.modules.catalog.query import build_catalog_query_spec, query_catalog_facets, query_catalog_items
from app.modules.catalog.schemas import ItemCreate, ManufacturerCreate
from app.modules.catalog.service import CatalogValidationError, create_item, create_manufacturer
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


async def transceiver(db, marker, reach, category="transceiver_ethernet"):
    manufacturer = await create_manufacturer(db, ManufacturerCreate(name=uuid.uuid4().hex))
    return await create_item(db, ItemCreate(category_key=category, name=marker,
        manufacturer_id=manufacturer.id, model=uuid.uuid4().hex, attributes={
            "speed": "10 Гбит/с", "wavelength": "1310 нм", "reach": reach,
            "form_factor": "SFP+", "fiber": "SMF", "connector": "LC"}))


async def test_hierarchy_long_range_and_shared_family_facets(warehouse_db):
    db = warehouse_db
    marker = uuid.uuid4().hex
    short = await transceiver(db, marker, "до 300 м")
    boundary = await transceiver(db, marker, "до 2 км")
    far = await transceiver(db, marker, "до 10 км", "transceiver_fc")
    spec = await build_catalog_query_spec(db, q=marker, category_key="transceivers")
    page = await query_catalog_items(db, spec, limit=20, offset=0)
    assert {r.record.item.id for r in page.items} == {short, boundary, far}
    spec = await build_catalog_query_spec(db, q=marker, category_key="transceivers", long_range=True)
    page = await query_catalog_items(db, spec, limit=20, offset=0)
    assert {r.record.item.id for r in page.items} == {boundary, far}
    facets = {f.key: f for f in await query_catalog_facets(db, spec)}
    assert "speed" not in facets and "connector" not in facets
    assert facets["reach_m"].minimum == 2000 and facets["reach_m"].maximum == 10000
    # Family filter resolves matching metadata for both children.
    spec = await build_catalog_query_spec(db, q=marker, category_key="transceivers",
        filter_expressions=["reach_m:gte:2000"])
    assert (await query_catalog_items(db, spec, limit=20, offset=0)).total == 2


async def test_scoped_facets_free_text_and_pagination(warehouse_db):
    db = warehouse_db
    marker = uuid.uuid4().hex
    ids = []
    for color, length in [("pearlescent", "5"), ("blue", "5"), ("blue", "7")]:
        payload = cable_payload(color=color + marker, length_m=length)
        payload.name = marker
        ids.append(await create_item(db, payload))
    spec = await build_catalog_query_spec(db, q=marker, category_key="optical_patch_cord")
    facets = {f.key: f for f in await query_catalog_facets(db, spec)}
    assert {v.value for v in facets["color"].values} == {"pearlescent"+marker, "blue"+marker}
    assert "fiber" not in facets and "ports" not in facets
    assert facets["length_m"].minimum == 5 and facets["length_m"].maximum == 7
    pages = [await query_catalog_items(db, spec, limit=1, offset=i) for i in range(3)]
    assert all(p.total == 3 for p in pages)
    assert {p.items[0].record.item.id for p in pages} == set(ids)
    spec = await build_catalog_query_spec(db, q=marker, category_key="optical_patch_cord",
        filter_expressions=["color:eq:blue"+marker, "length_m:gte:6"])
    assert [r.record.item.id for r in (await query_catalog_items(db, spec, limit=20, offset=0)).items] == [ids[2]]


@pytest.mark.parametrize("expressions", [["ports:eq:2"], ["color:gte:blue"],
    ["length_m:gte:abc"], ["bad"], ["length_m:gte:1", "length_m:gte:2"]])
async def test_invalid_filters_are_rejected(warehouse_db, expressions):
    with pytest.raises(CatalogValidationError):
        await build_catalog_query_spec(warehouse_db, category_key="optical_patch_cord",
            filter_expressions=expressions)


@pytest.mark.parametrize("reach", ["unknown", "до 2 км experimental", "10/20 км"])
async def test_ambiguous_reach_rejected(warehouse_db, reach):
    with pytest.raises(CatalogValidationError, match="reach"):
        await transceiver(warehouse_db, uuid.uuid4().hex, reach)
