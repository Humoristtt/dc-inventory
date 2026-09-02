import os
import uuid
from datetime import UTC, datetime
from typing import TypedDict, Unpack

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.enums import AccountingMode, ItemStatus
from app.modules.catalog.models import Category, Item, Manufacturer
from app.modules.catalog.query import (
    FacetRecord,
    build_catalog_query_spec,
    query_catalog_facets,
    query_catalog_items,
)
from app.modules.catalog.schemas import ItemCreate, ManufacturerCreate
from app.modules.catalog.service import (
    CatalogValidationError,
    create_item,
    create_manufacturer,
    normalize_comparison,
)
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User
from app.modules.inventory.enums import InventoryUnitState, LocationStatus
from app.modules.inventory.models import InventoryUnit, Location, StockBalance
from app.modules.inventory.service import normalize_identity

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)


class QueryArgs(TypedDict, total=False):
    q: str | None
    category_key: str | None
    item_status: ItemStatus
    manufacturer_ids: list[uuid.UUID]
    availability: str
    location_ids: list[uuid.UUID]
    sort: str
    order: str
    filter_expressions: list[str]


async def _item(
    db: AsyncSession,
    marker: str,
    category_key: str,
    name: str,
    attributes: dict[str, object],
    *,
    manufacturer_id: uuid.UUID | None = None,
    model: str | None = None,
    internal_code: str | None = None,
) -> uuid.UUID:
    return await create_item(
        db,
        ItemCreate.model_validate(
            {
                "category_key": category_key,
                "manufacturer_id": manufacturer_id,
                "name": f"{name} {marker}",
                "model": model,
                "internal_code": internal_code,
                "attributes": attributes,
            }
        ),
    )


def _facet_by_key(facets: list[FacetRecord], key: str) -> FacetRecord:
    return next(facet for facet in facets if facet.key == key)


@pytest.mark.asyncio
async def test_stage7_search_filters_inventory_facets_and_pagination() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            transaction = await db.begin()
            try:
                cisco = await create_manufacturer(db, ManufacturerCreate(name=f"Cisco {marker}"))
                finisar = await create_manufacturer(
                    db, ManufacturerCreate(name=f"Finisar {marker}")
                )
                seagate = await create_manufacturer(
                    db, ManufacturerCreate(name=f"Seagate {marker}")
                )

                sfp_cisco_1g = await _item(
                    db,
                    marker,
                    "sfp",
                    "Cisco 1G optic",
                    {
                        "form_factor": "SFP",
                        "speed_mbps": 1000,
                        "medium": "SMF",
                        "reach_class": "LR",
                        "reach_m": 10000,
                        "connector": "LC Duplex",
                        "dom_ddm": False,
                    },
                    manufacturer_id=cisco.id,
                )
                sfp_cisco_10g = await _item(
                    db,
                    marker,
                    "sfp",
                    "Cisco 10G optic",
                    {
                        "form_factor": "SFP+",
                        "speed_mbps": 10000,
                        "medium": "SMF",
                        "reach_class": "LR",
                        "reach_m": 10000,
                        "connector": "LC Duplex",
                        "dom_ddm": True,
                    },
                    manufacturer_id=cisco.id,
                )
                sfp_finisar_10g = await _item(
                    db,
                    marker,
                    "sfp",
                    "Finisar 10G optic",
                    {
                        "form_factor": "SFP+",
                        "speed_mbps": 10000,
                        "medium": "MMF",
                        "reach_class": "SR",
                        "reach_m": 300,
                        "connector": "LC Duplex",
                        "dom_ddm": False,
                    },
                    manufacturer_id=finisar.id,
                )
                sfp_finisar_25g = await _item(
                    db,
                    marker,
                    "sfp",
                    "Finisar 25G optic",
                    {
                        "form_factor": "SFP28",
                        "speed_mbps": 25000,
                        "medium": "SMF",
                        "reach_class": "LR",
                        "reach_m": 10000,
                        "connector": "LC Simplex",
                        "dom_ddm": True,
                    },
                    manufacturer_id=finisar.id,
                )
                optics = await _item(
                    db,
                    marker,
                    "optics",
                    "Оптический патч-корд",
                    {
                        "product_type": "Patch cord",
                        "fiber_mode": "SM",
                        "fiber_standard": "OS2",
                        "connector_a": "LC",
                        "polish_a": "UPC",
                        "connector_b": "SC",
                        "polish_b": "APC",
                        "fiber_count": 2,
                        "length_m": "3.5",
                        "color": "Yellow",
                    },
                )
                power = await _item(
                    db,
                    marker,
                    "power_cable",
                    "Power lead",
                    {
                        "connector_a": "IEC C13",
                        "connector_b": "IEC C14",
                        "length_m": "2",
                        "color": "Red",
                        "rated_current_a": "10",
                        "rated_voltage_v": 250,
                        "conductor_count": 3,
                        "conductor_cross_section_mm2": "1.5",
                    },
                )
                copper = await _item(
                    db,
                    marker,
                    "copper_network_cable",
                    "Copper patch cord",
                    {
                        "connector_a": "RJ45",
                        "connector_b": "RJ45",
                        "length_m": "5",
                        "cable_category": "Cat 6A",
                        "shielding": "S/FTP",
                    },
                    internal_code=f"rack:{marker}",
                )
                nic = await _item(
                    db,
                    marker,
                    "nic",
                    "Intel adapter",
                    {
                        "port_count": 2,
                        "port_speed_mbps": 25000,
                        "media_type": "SFP28",
                        "pcie_generation": "Gen4",
                        "pcie_lanes": 8,
                        "protocol": "Ethernet",
                        "bracket": "full_profile",
                        "sriov": True,
                        "rdma_roce": False,
                    },
                    model="X710",
                )
                disk = await _item(
                    db,
                    marker,
                    "disk",
                    "Seagate SSD",
                    {
                        "drive_type": "SSD",
                        "capacity_bytes": 1_920_383_410_176,
                        "form_factor": "2.5",
                        "interface": "SAS",
                        "interface_speed_mbps": 12000,
                        "rpm": 7200,
                        "sector_format": "4Kn",
                    },
                    manufacturer_id=seagate.id,
                )
                percent = await _item(
                    db,
                    marker,
                    "sfp",
                    "Literal % module",
                    {"speed_mbps": 1000},
                )
                archived = await _item(
                    db,
                    marker,
                    "sfp",
                    "Archived module",
                    {"speed_mbps": 1000},
                )
                archived_item = await db.get(Item, archived)
                assert archived_item is not None
                archived_item.status = ItemStatus.ARCHIVED
                archived_item.archived_at = datetime.now(UTC)

                holder = User(
                    id=uuid.uuid4(),
                    role=UserRole.USER,
                    access_status=UserAccessStatus.APPROVED,
                    approved_at=datetime.now(UTC),
                )
                location_a = Location(
                    id=uuid.uuid4(),
                    code=f"A-{marker[:8]}",
                    normalized_code=f"a-{marker[:8]}",
                    name="Warehouse A",
                    status=LocationStatus.ACTIVE,
                )
                location_b = Location(
                    id=uuid.uuid4(),
                    code=f"B-{marker[:8]}",
                    normalized_code=f"b-{marker[:8]}",
                    name="Warehouse B",
                    status=LocationStatus.ACTIVE,
                )
                location_other = Location(
                    id=uuid.uuid4(),
                    code=f"Z-{marker[:8]}",
                    normalized_code=f"z-{marker[:8]}",
                    name="Other warehouse",
                    status=LocationStatus.ACTIVE,
                )
                db.add_all([holder, location_a, location_b, location_other])
                await db.flush()
                db.add_all(
                    [
                        StockBalance(
                            item_id=sfp_cisco_10g,
                            location_id=location_a.id,
                            quantity=5,
                        ),
                        StockBalance(
                            item_id=sfp_cisco_10g,
                            location_id=location_b.id,
                            quantity=3,
                        ),
                        StockBalance(
                            item_id=sfp_cisco_10g,
                            holder_user_id=holder.id,
                            quantity=2,
                        ),
                        StockBalance(
                            item_id=optics,
                            location_id=location_b.id,
                            quantity=1,
                        ),
                        StockBalance(
                            item_id=power,
                            location_id=location_a.id,
                            quantity=4,
                        ),
                    ]
                )

                serial_units = [
                    (
                        "ABC12345",
                        "5000CCA000000001",
                        InventoryUnitState.STORED,
                        location_a.id,
                        None,
                    ),
                    (
                        "ABC12345-B",
                        "5000CCA000000002",
                        InventoryUnitState.STORED,
                        location_a.id,
                        None,
                    ),
                    ("NIC-B-1", "5000CCA000000003", InventoryUnitState.STORED, location_b.id, None),
                    ("NIC-I-1", None, InventoryUnitState.ISSUED, None, holder.id),
                    ("NIC-I-2", None, InventoryUnitState.ISSUED, None, holder.id),
                    ("HIST-WRITTEN", None, InventoryUnitState.WRITTEN_OFF, None, None),
                    ("HIST-VOIDED", None, InventoryUnitState.VOIDED, None, None),
                ]
                for serial_number, wwn, state, location_id, holder_id in serial_units:
                    db.add(
                        InventoryUnit(
                            item_id=nic,
                            serial_number=serial_number,
                            normalized_serial_number=normalize_identity(
                                serial_number,
                                field="serial_number",
                                max_length=255,
                            ),
                            wwn=wwn,
                            normalized_wwn=(
                                normalize_identity(wwn, field="wwn", max_length=255)
                                if wwn is not None
                                else None
                            ),
                            state=state,
                            current_location_id=location_id,
                            current_holder_user_id=holder_id,
                        )
                    )
                db.add(
                    InventoryUnit(
                        item_id=disk,
                        serial_number="DISK-ISSUED-1",
                        normalized_serial_number="disk-issued-1",
                        wwn="5000CCA099999999",
                        normalized_wwn="5000cca099999999",
                        state=InventoryUnitState.ISSUED,
                        current_holder_user_id=holder.id,
                    )
                )
                await db.flush()

                async def ids(**kwargs: Unpack[QueryArgs]) -> list[uuid.UUID]:
                    spec = await build_catalog_query_spec(db, **kwargs)
                    page = await query_catalog_items(db, spec, limit=100, offset=0)
                    return [entry.record.item.id for entry in page.items]

                assert set(await ids(q=f"FiNiSaR   {marker} LR")) == {sfp_finisar_25g}
                assert await ids(q="C13 C14") == [power]
                assert await ids(q="abc12345") == [nic]
                assert await ids(q="5000cca000000001") == [nic]
                assert await ids(q="HIST-WRITTEN") == [nic]
                assert await ids(q="HIST-VOIDED") == [nic]
                assert await ids(q="disk-issued-1") == [disk]
                assert await ids(q="5000cca099999999") == [disk]
                assert await ids(q=f"RACK:{marker.upper()}") == [copper]
                assert await ids(q=f"{marker} :") == [copper]
                assert await ids(q="ОПТИЧЕСКИЙ") == [optics]
                assert await ids(q=f"{marker} _") == [nic]
                assert await ids(q=f"{marker} %") == [percent]

                assert set(await ids(category_key="sfp", manufacturer_ids=[finisar.id])) == {
                    sfp_finisar_10g,
                    sfp_finisar_25g,
                }
                assert set(
                    await ids(category_key="sfp", manufacturer_ids=[cisco.id, finisar.id])
                ) == {
                    sfp_cisco_1g,
                    sfp_cisco_10g,
                    sfp_finisar_10g,
                    sfp_finisar_25g,
                }
                assert set(
                    await ids(
                        category_key="sfp",
                        filter_expressions=["speed_mbps:eq:10000"],
                    )
                ) == {sfp_cisco_10g, sfp_finisar_10g}
                assert await ids(
                    category_key="sfp",
                    manufacturer_ids=[finisar.id],
                    filter_expressions=["speed_mbps:eq:10000"],
                ) == [sfp_finisar_10g]
                assert set(
                    await ids(
                        category_key="sfp",
                        filter_expressions=["reach_m:gte:10000"],
                    )
                ) == {sfp_cisco_1g, sfp_cisco_10g, sfp_finisar_25g}
                assert set(
                    await ids(
                        category_key="sfp",
                        filter_expressions=[
                            "reach_m:gte:300",
                            "reach_m:lte:9999",
                        ],
                    )
                ) == {sfp_finisar_10g}
                assert set(
                    await ids(
                        category_key="sfp",
                        filter_expressions=[
                            "form_factor:eq:SFP+",
                            "form_factor:eq:SFP28",
                        ],
                    )
                ) == {sfp_cisco_10g, sfp_finisar_10g, sfp_finisar_25g}
                assert set(
                    await ids(
                        category_key="sfp",
                        filter_expressions=[
                            "medium:eq:SMF",
                            "connector:eq:LC Duplex",
                            "dom_ddm:eq:true",
                        ],
                    )
                ) == {sfp_cisco_10g}
                assert set(
                    await ids(
                        category_key="sfp",
                        filter_expressions=["dom_ddm:eq:false"],
                    )
                ) == {sfp_cisco_1g, sfp_finisar_10g}

                assert await ids(
                    category_key="optics",
                    filter_expressions=[
                        "fiber_mode:eq:SM",
                        "fiber_standard:eq:OS2",
                        "connector_a:eq:lc",
                        "polish_b:eq:APC",
                        "length_m:gte:3",
                        "length_m:lte:4",
                    ],
                    location_ids=[location_b.id],
                    availability="IN_STOCK",
                ) == [optics]
                assert await ids(
                    category_key="power_cable",
                    filter_expressions=[
                        "connector_a:eq:iec c13",
                        "connector_b:eq:IEC C14",
                        "length_m:gte:1",
                        "length_m:lte:3",
                        "color:eq:red",
                        "rated_current_a:eq:10",
                    ],
                    location_ids=[location_a.id],
                ) == [power]
                assert await ids(
                    category_key="copper_network_cable",
                    q="RJ45 S/FTP",
                    filter_expressions=[
                        "cable_category:eq:cat 6a",
                        "length_m:lte:5",
                    ],
                ) == [copper]
                assert await ids(
                    category_key="nic",
                    filter_expressions=[
                        "port_count:eq:2",
                        "port_speed_mbps:eq:25000",
                        "media_type:eq:SFP28",
                        "pcie_generation:eq:gen4",
                        "pcie_lanes:eq:8",
                        "protocol:eq:Ethernet",
                        "bracket:eq:full_profile",
                    ],
                ) == [nic]
                assert await ids(
                    category_key="disk",
                    manufacturer_ids=[seagate.id],
                    filter_expressions=[
                        "drive_type:eq:SSD",
                        "capacity_bytes:gte:1920000000000",
                        "interface:eq:SAS",
                        "form_factor:eq:2.5",
                        "rpm:eq:7200",
                    ],
                ) == [disk]
                assert await ids(category_key="disk", q="1.92TB") == []

                quantity_spec = await build_catalog_query_spec(db, q=f"Cisco 10G {marker}")
                quantity_page = await query_catalog_items(db, quantity_spec, limit=10, offset=0)
                assert quantity_page.items[0].inventory.available_count == 8
                assert quantity_page.items[0].inventory.custody_count == 2
                assert quantity_page.items[0].inventory.total_count == 10
                assert await ids(location_ids=[location_a.id], q=f"Cisco 10G {marker}") == [
                    sfp_cisco_10g
                ]
                assert await ids(location_ids=[location_other.id], q=f"Cisco 10G {marker}") == []
                assert await ids(availability="IN_STOCK", q=f"Cisco 10G {marker}") == [
                    sfp_cisco_10g
                ]
                serial_spec = await build_catalog_query_spec(db, q=f"Intel adapter {marker}")
                serial_page = await query_catalog_items(db, serial_spec, limit=10, offset=0)
                assert serial_page.items[0].inventory.available_count == 3
                assert serial_page.items[0].inventory.custody_count == 2
                assert serial_page.items[0].inventory.total_count == 5
                assert await ids(location_ids=[location_a.id], q=f"Intel adapter {marker}") == [nic]
                assert await ids(location_ids=[location_b.id], q=f"Intel adapter {marker}") == [nic]
                assert await ids(availability="OUT_OF_STOCK", q=f"Seagate SSD {marker}") == [disk]
                assert await ids(availability="IN_STOCK", q=f"Seagate SSD {marker}") == []
                assert await ids(item_status=ItemStatus.ARCHIVED, q=marker) == [archived]

                default_name_page = await query_catalog_items(
                    db, await build_catalog_query_spec(db, q=marker), limit=100, offset=0
                )
                explicit_name_page = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(db, q=marker, sort="name", order="asc"),
                    limit=100,
                    offset=0,
                )
                name_desc_page = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(db, q=marker, sort="name", order="desc"),
                    limit=100,
                    offset=0,
                )
                default_name_ids = [entry.record.item.id for entry in default_name_page.items]
                explicit_name_ids = [entry.record.item.id for entry in explicit_name_page.items]
                name_desc_ids = [entry.record.item.id for entry in name_desc_page.items]
                assert default_name_ids == explicit_name_ids
                assert name_desc_ids == list(reversed(default_name_ids))

                manufacturer_asc = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(
                        db,
                        q=marker,
                        manufacturer_ids=[cisco.id, finisar.id, seagate.id],
                        sort="manufacturer",
                        order="asc",
                    ),
                    limit=100,
                    offset=0,
                )
                assert [entry.record.item.id for entry in manufacturer_asc.items] == [
                    sfp_cisco_10g,
                    sfp_cisco_1g,
                    sfp_finisar_10g,
                    sfp_finisar_25g,
                    disk,
                ]

                manufacturer_desc = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(
                        db,
                        q=marker,
                        manufacturer_ids=[cisco.id, finisar.id, seagate.id],
                        sort="manufacturer",
                        order="desc",
                    ),
                    limit=100,
                    offset=0,
                )
                assert [entry.record.item.id for entry in manufacturer_desc.items] == [
                    disk,
                    sfp_finisar_25g,
                    sfp_finisar_10g,
                    sfp_cisco_1g,
                    sfp_cisco_10g,
                ]

                manufacturer_with_nulls = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(
                        db, q=marker, sort="manufacturer", order="asc"
                    ),
                    limit=100,
                    offset=0,
                )
                null_seen = False
                for entry in manufacturer_with_nulls.items:
                    if entry.record.manufacturer is None:
                        null_seen = True
                    else:
                        assert not null_seen

                total_desc = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(db, q=marker, sort="total", order="desc"),
                    limit=100,
                    offset=0,
                )
                assert [entry.record.item.id for entry in total_desc.items[:3]] == [
                    sfp_cisco_10g,
                    nic,
                    power,
                ]

                total_asc = await query_catalog_items(
                    db,
                    await build_catalog_query_spec(db, q=marker, sort="total", order="asc"),
                    limit=100,
                    offset=0,
                )
                assert [entry.record.item.id for entry in total_asc.items[-3:]] == [
                    power,
                    nic,
                    sfp_cisco_10g,
                ]

                all_spec = await build_catalog_query_spec(
                    db, q=marker, sort="available", order="desc"
                )
                first = await query_catalog_items(db, all_spec, limit=3, offset=0)
                second = await query_catalog_items(db, all_spec, limit=3, offset=3)
                beyond = await query_catalog_items(db, all_spec, limit=3, offset=100)
                repeated = await query_catalog_items(db, all_spec, limit=3, offset=0)
                assert first.total == second.total == beyond.total == 10
                assert beyond.items == []
                assert [entry.record.item.id for entry in first.items] == [
                    entry.record.item.id for entry in repeated.items
                ]
                assert not (
                    {entry.record.item.id for entry in first.items}
                    & {entry.record.item.id for entry in second.items}
                )

                facet_spec = await build_catalog_query_spec(
                    db,
                    category_key="sfp",
                    manufacturer_ids=[finisar.id],
                    filter_expressions=["speed_mbps:eq:10000"],
                )
                facets = await query_catalog_facets(db, facet_spec)
                manufacturer_facet = _facet_by_key(facets, "manufacturer")
                manufacturer_counts = {
                    value.value: value.count for value in manufacturer_facet.values
                }
                assert manufacturer_counts[cisco.id] == 1
                assert manufacturer_counts[finisar.id] == 1
                speed = _facet_by_key(facets, "speed_mbps")
                assert speed.minimum == 10000
                assert speed.maximum == 25000
                form_factor = _facet_by_key(facets, "form_factor")
                assert [value.value for value in form_factor.values] == ["SFP+"]
                assert "vendor_compatibility" not in {facet.key for facet in facets}

                self_excluding_exact = await query_catalog_facets(
                    db,
                    await build_catalog_query_spec(
                        db,
                        category_key="sfp",
                        manufacturer_ids=[finisar.id],
                        filter_expressions=["form_factor:eq:SFP+"],
                    ),
                )
                assert [
                    value.value
                    for value in _facet_by_key(self_excluding_exact, "form_factor").values
                ] == ["SFP+", "SFP28"]

                sfp_facets = await query_catalog_facets(
                    db, await build_catalog_query_spec(db, category_key="sfp")
                )
                assert [
                    value.value for value in _facet_by_key(sfp_facets, "form_factor").values
                ] == ["SFP", "SFP+", "SFP28"]
                assert [value.value for value in _facet_by_key(sfp_facets, "dom_ddm").values] == [
                    False,
                    True,
                ]
                sfp_reach = _facet_by_key(sfp_facets, "reach_m")
                assert sfp_reach.minimum == 300
                assert sfp_reach.maximum == 10000

                location_self_excluding = await query_catalog_facets(
                    db,
                    await build_catalog_query_spec(
                        db,
                        q=f"Cisco 10G {marker}",
                        location_ids=[location_a.id],
                    ),
                )
                assert {
                    value.value
                    for value in _facet_by_key(location_self_excluding, "location").values
                } == {location_a.id, location_b.id}

                common_facets = await query_catalog_facets(
                    db, await build_catalog_query_spec(db, q=marker)
                )
                category_facet = _facet_by_key(common_facets, "category")
                assert {value.value for value in category_facet.values} == {
                    "sfp",
                    "optics",
                    "power_cable",
                    "copper_network_cable",
                    "nic",
                    "disk",
                }
                assert _facet_by_key(common_facets, "location").values
                assert _facet_by_key(common_facets, "availability").values

                empty_facets = await query_catalog_facets(
                    db,
                    await build_catalog_query_spec(db, category_key="sfp", q="definitely-no-match"),
                )
                empty_reach = _facet_by_key(empty_facets, "reach_m")
                assert empty_reach.minimum is None
                assert empty_reach.maximum is None
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stage7_controlled_query_validation() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as db:
            cases: list[tuple[QueryArgs, str]] = [
                ({"filter_expressions": ["speed_mbps:eq:10000"]}, "filter_category_required"),
                ({"category_key": "sfp", "filter_expressions": ["broken"]}, "filter_malformed"),
                (
                    {"category_key": "sfp", "filter_expressions": ["unknown:eq:x"]},
                    "filter_unknown_attribute",
                ),
                (
                    {"category_key": "sfp", "filter_expressions": ["vendor_compatibility:eq:x"]},
                    "filter_not_filterable",
                ),
                (
                    {"category_key": "sfp", "filter_expressions": ["medium:gte:SMF"]},
                    "filter_operator_not_allowed",
                ),
                (
                    {"category_key": "sfp", "filter_expressions": ["speed_mbps:eq:true"]},
                    "filter_value_invalid",
                ),
                (
                    {
                        "category_key": "sfp",
                        "filter_expressions": ["reach_m:gte:1", "reach_m:gte:2"],
                    },
                    "filter_range_boundary_conflict",
                ),
                ({"availability": "sometimes"}, "availability_invalid"),
                ({"sort": "random"}, "sort_invalid"),
                ({"order": "sideways"}, "order_invalid"),
            ]
            for kwargs, expected_code in cases:
                with pytest.raises(CatalogValidationError) as caught:
                    await build_catalog_query_spec(db, **kwargs)
                assert caught.value.code == expected_code
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stage7_query_normalization_uses_casefolded_catalog_identity() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    marker = uuid.uuid4().hex
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            transaction = await db.begin()
            try:
                category_id = await db.scalar(select(Category.id).where(Category.key == "sfp"))
                assert category_id is not None
                manufacturer = Manufacturer(
                    id=uuid.uuid4(),
                    name=f"Straße {marker}",
                    normalized_name=normalize_comparison(f"Straße {marker}"),
                )
                item = Item(
                    id=uuid.uuid4(),
                    category_id=category_id,
                    manufacturer_id=manufacturer.id,
                    name=f"Casefold item {marker}",
                    normalized_name=normalize_comparison(f"Casefold item {marker}"),
                    accounting_mode=AccountingMode.QUANTITY,
                    status=ItemStatus.ACTIVE,
                )
                db.add_all([manufacturer, item])
                await db.flush()
                spec = await build_catalog_query_spec(db, q=f"STRASSE {marker}")
                page = await query_catalog_items(db, spec, limit=10, offset=0)
                assert [entry.record.item.id for entry in page.items] == [item.id]
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
