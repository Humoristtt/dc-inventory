import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.enums import (
    AccountingMode,
    AttributeDataType,
    FilterType,
    ItemStatus,
)
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
from app.modules.catalog.service import (
    CatalogValidationError,
    check_duplicate_candidates,
    create_item,
    create_manufacturer,
    get_category_record,
    get_item_record,
    list_items,
    set_item_archived,
    update_item,
)

DATABASE_URL = os.environ["DATABASE_URL"]
POSTGRES_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_ENABLED,
    reason="set RUN_POSTGRES_INTEGRATION=1 against a migrated PostgreSQL test DB",
)


@pytest.mark.asyncio
async def test_stage5_migration_seeded_five_system_category_schemas() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            expected_modes = {
                "sfp": AccountingMode.QUANTITY,
                "optics": AccountingMode.QUANTITY,
                "power_cable": AccountingMode.QUANTITY,
                "nic": AccountingMode.SERIAL,
                "disk": AccountingMode.SERIAL,
            }
            categories = list(
                (
                    await db.scalars(
                        select(Category).where(Category.key.in_(expected_modes))
                    )
                ).all()
            )
            assert {
                category.key: category.default_accounting_mode
                for category in categories
            } == expected_modes
            assert all(category.is_system for category in categories)

            sfp = await get_category_record(db, "sfp")
            sfp_by_key = {attribute.key: attribute for attribute in sfp.attributes}
            assert sfp_by_key["speed_mbps"].required is True
            assert sfp_by_key["speed_mbps"].filterable is True
            assert sfp_by_key["speed_mbps"].searchable is True
            assert sfp_by_key["speed_mbps"].unit == "Mbps"
            assert {
                "SFP",
                "SFP+",
                "SFP28",
                "QSFP+",
                "QSFP28",
                "QSFP56",
                "QSFP-DD",
            } <= set(sfp_by_key["form_factor"].allowed_values or [])

            disk = await get_category_record(db, "disk")
            disk_by_key = {attribute.key: attribute for attribute in disk.attributes}
            assert disk_by_key["capacity_bytes"].data_type == AttributeDataType.INTEGER
            assert disk_by_key["capacity_bytes"].unit == "bytes"
            assert disk_by_key["capacity_bytes"].excel_visible is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_source_reference_refinement_metadata_is_versioned() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            sfp = await get_category_record(db, "sfp")
            sfp_by_key = {attribute.key: attribute for attribute in sfp.attributes}
            assert {"XFP"} <= set(
                sfp_by_key["form_factor"].allowed_values or []
            )
            assert {"SC Simplex"} <= set(
                sfp_by_key["connector"].allowed_values or []
            )
            assert {"MPO", "MPO/PC"} <= set(
                sfp_by_key["connector"].allowed_values or []
            )
            assert sfp_by_key["speed_profile"].data_type == AttributeDataType.TEXT
            assert sfp_by_key["speed_profile"].searchable is True
            assert sfp_by_key["speed_profile"].validation_metadata == {
                "max_length": 255,
                "preserve_whitespace": True,
            }
            assert sfp_by_key["reach_profile"].validation_metadata == {
                "max_length": 2000,
                "preserve_whitespace": True,
            }
            assert sfp_by_key["wavelength_profile"].data_type == (
                AttributeDataType.TEXT
            )
            assert sfp_by_key["nominal_wavelength_nm"].data_type == (
                AttributeDataType.DECIMAL
            )
            assert sfp_by_key["nominal_wavelength_nm"].unit == "nm"
            assert sfp_by_key["nominal_wavelength_nm"].filterable is True

            power = await get_category_record(db, "power_cable")
            power_by_key = {
                attribute.key: attribute for attribute in power.attributes
            }
            assert power_by_key["conductor_count"].data_type == (
                AttributeDataType.INTEGER
            )
            assert power_by_key["conductor_count"].required is False
            assert power_by_key["conductor_cross_section_mm2"].data_type == (
                AttributeDataType.DECIMAL
            )
            assert power_by_key["conductor_cross_section_mm2"].unit == "mm2"

            copper = await get_category_record(db, "copper_network_cable")
            assert copper.category.default_accounting_mode == (
                AccountingMode.QUANTITY
            )
            assert copper.category.is_system is True
            copper_by_key = {
                attribute.key: attribute for attribute in copper.attributes
            }
            assert {
                "connector_a",
                "connector_b",
                "length_m",
                "cable_category",
                "shielding",
            } <= set(copper_by_key)
            assert copper_by_key["length_m"].data_type == (
                AttributeDataType.DECIMAL
            )
            assert copper_by_key["length_m"].unit == "m"
            assert copper_by_key["cable_category"].data_type == (
                AttributeDataType.TEXT
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_database_constraints_and_restrictive_foreign_keys() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    category_one_id = uuid.uuid4()
    category_two_id = uuid.uuid4()
    manufacturer_id = uuid.uuid4()
    attribute_one_id = uuid.uuid4()
    attribute_two_id = uuid.uuid4()
    attribute_three_id = uuid.uuid4()
    item_id = uuid.uuid4()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            transaction = await db.begin()
            try:
                category_one = Category(
                    id=category_one_id,
                    key=f"test-{category_one_id}",
                    display_name="Test category one",
                    default_accounting_mode=AccountingMode.QUANTITY,
                    sort_order=1000,
                    is_system=False,
                )
                category_two = Category(
                    id=category_two_id,
                    key=f"test-{category_two_id}",
                    display_name="Test category two",
                    default_accounting_mode=AccountingMode.QUANTITY,
                    sort_order=1001,
                    is_system=False,
                )
                manufacturer = Manufacturer(
                    id=manufacturer_id,
                    name="Constraint Manufacturer",
                    normalized_name=f"constraint manufacturer {manufacturer_id}",
                )
                attribute_one = CategoryAttribute(
                    id=attribute_one_id,
                    category_id=category_one_id,
                    key="value",
                    label="Value",
                    data_type=AttributeDataType.TEXT,
                    required=False,
                    filterable=False,
                    searchable=False,
                    card_visible=False,
                    detail_visible=True,
                    table_visible=False,
                    excel_visible=True,
                    sort_order=10,
                    filter_type=FilterType.NONE,
                    is_system=False,
                )
                attribute_two = CategoryAttribute(
                    id=attribute_two_id,
                    category_id=category_two_id,
                    key="value",
                    label="Value",
                    data_type=AttributeDataType.TEXT,
                    required=False,
                    filterable=False,
                    searchable=False,
                    card_visible=False,
                    detail_visible=True,
                    table_visible=False,
                    excel_visible=True,
                    sort_order=10,
                    filter_type=FilterType.NONE,
                    is_system=False,
                )
                attribute_three = CategoryAttribute(
                    id=attribute_three_id,
                    category_id=category_one_id,
                    key="other_value",
                    label="Other value",
                    data_type=AttributeDataType.TEXT,
                    required=False,
                    filterable=False,
                    searchable=False,
                    card_visible=False,
                    detail_visible=True,
                    table_visible=False,
                    excel_visible=True,
                    sort_order=20,
                    filter_type=FilterType.NONE,
                    is_system=False,
                )
                item = Item(
                    id=item_id,
                    category_id=category_one_id,
                    manufacturer_id=manufacturer_id,
                    name="Constraint item",
                    normalized_name=f"constraint item {item_id}",
                    accounting_mode=AccountingMode.QUANTITY,
                    status=ItemStatus.ACTIVE,
                )
                db.add_all(
                    [
                        category_one,
                        category_two,
                        manufacturer,
                        attribute_one,
                        attribute_two,
                        attribute_three,
                        item,
                    ]
                )
                await db.flush()
                db.add(
                    ItemAttributeValue(
                        id=uuid.uuid4(),
                        item_id=item_id,
                        category_id=category_one_id,
                        category_attribute_id=attribute_one_id,
                        text_value="stored",
                    )
                )
                await db.flush()

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(Category).values(
                                id=uuid.uuid4(),
                                key=category_one.key,
                                display_name="Duplicate category",
                                default_accounting_mode="QUANTITY",
                                sort_order=1,
                                is_system=False,
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(Manufacturer).values(
                                id=uuid.uuid4(),
                                name="Different display",
                                normalized_name=manufacturer.normalized_name,
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(CategoryAttribute).values(
                                id=uuid.uuid4(),
                                category_id=category_one_id,
                                key=attribute_one.key,
                                label="Duplicate key",
                                data_type="TEXT",
                                required=False,
                                filterable=False,
                                searchable=False,
                                card_visible=False,
                                detail_visible=True,
                                table_visible=False,
                                excel_visible=True,
                                sort_order=20,
                                filter_type="NONE",
                                is_system=False,
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(ItemAttributeValue).values(
                                id=uuid.uuid4(),
                                item_id=item_id,
                                category_id=category_one_id,
                                category_attribute_id=attribute_one_id,
                                text_value="duplicate",
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(ItemAttributeValue).values(
                                id=uuid.uuid4(),
                                item_id=item_id,
                                category_id=category_one_id,
                                category_attribute_id=attribute_three_id,
                                text_value="two",
                                integer_value=2,
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(ItemAttributeValue).values(
                                id=uuid.uuid4(),
                                item_id=item_id,
                                category_id=category_one_id,
                                category_attribute_id=attribute_two_id,
                                text_value="cross-category",
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            text(
                                "INSERT INTO items "
                                "(id, category_id, name, normalized_name, "
                                "accounting_mode, status) "
                                "VALUES (:id, :category_id, :name, "
                                ":normalized_name, :accounting_mode, :status)"
                            ),
                            {
                                "id": uuid.uuid4(),
                                "category_id": category_one_id,
                                "name": "Invalid accounting",
                                "normalized_name": (
                                    f"invalid accounting {uuid.uuid4()}"
                                ),
                                "accounting_mode": "INVALID",
                                "status": "ACTIVE",
                            },
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            insert(Item).values(
                                id=uuid.uuid4(),
                                category_id=category_one_id,
                                name="Invalid archive state",
                                normalized_name=f"invalid archive {uuid.uuid4()}",
                                accounting_mode="QUANTITY",
                                status="ARCHIVED",
                                archived_at=None,
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            delete(Category).where(Category.id == category_one_id)
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            delete(Manufacturer).where(
                                Manufacturer.id == manufacturer_id
                            )
                        )

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(
                            delete(CategoryAttribute).where(
                                CategoryAttribute.id == attribute_one_id
                            )
                        )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_orm_delete_manufacturer_is_restricted_when_item_references_it() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    manufacturer_id = uuid.uuid4()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            transaction = await db.begin()
            try:
                category_id = await db.scalar(
                    select(Category.id).where(Category.key == "sfp")
                )
                assert category_id is not None

                manufacturer = Manufacturer(
                    id=manufacturer_id,
                    name="ORM Restrict Manufacturer",
                    normalized_name=f"orm restrict manufacturer {manufacturer_id}",
                )
                db.add_all(
                    [
                        manufacturer,
                        Item(
                            id=uuid.uuid4(),
                            category_id=category_id,
                            manufacturer_id=manufacturer_id,
                            name="ORM restrict item",
                            normalized_name=f"orm restrict item {manufacturer_id}",
                            accounting_mode=AccountingMode.QUANTITY,
                            status=ItemStatus.ACTIVE,
                        ),
                    ]
                )
                await db.flush()

                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        await db.delete(manufacturer)
                        await db.flush()
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_service_handles_all_versioned_categories_and_item_lifecycle() -> None:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    marker = uuid.uuid4().hex

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            transaction = await db.begin()
            try:
                manufacturer = await create_manufacturer(
                    db,
                    ManufacturerCreate(name=f"  Test   Manufacturer {marker} "),
                )
                assert manufacturer.name == f"Test Manufacturer {marker}"

                sfp_id = await create_item(
                    db,
                    ItemCreate(
                        category_key="sfp",
                        manufacturer_id=manufacturer.id,
                        name=f"SFP {marker}",
                        model="Model SFP",
                        manufacturer_part_number=" PN-100 ",
                        attributes={
                            "form_factor": "SFP+",
                            "speed_mbps": 10000,
                            "medium": "SMF",
                            "reach_class": "LR",
                            "reach_m": 10000,
                            "connector": "LC Duplex",
                            "tx_wavelength_nm": "1310.125",
                            "dom_ddm": True,
                            "vendor_compatibility": " Cisco   compatible ",
                        },
                    ),
                )
                optics_id = await create_item(
                    db,
                    ItemCreate(
                        category_key="optics",
                        name=f"Optics {marker}",
                        attributes={
                            "product_type": "Patch cord",
                            "fiber_mode": "SM",
                            "fiber_standard": "OS2",
                            "connector_a": "LC",
                            "polish_a": "UPC",
                            "connector_b": "LC",
                            "polish_b": "UPC",
                            "fiber_count": 2,
                            "length_m": "2.500",
                            "color": "Yellow",
                        },
                    ),
                )
                power_id = await create_item(
                    db,
                    ItemCreate(
                        category_key="power_cable",
                        name=f"Power cable {marker}",
                        model="C13-C14",
                        attributes={
                            "connector_a": "IEC C13",
                            "connector_b": "IEC C14",
                            "length_m": "2",
                            "color": "Red",
                            "rated_current_a": "10.0",
                            "rated_voltage_v": 250,
                        },
                    ),
                )
                copper_id = await create_item(
                    db,
                    ItemCreate(
                        category_key="copper_network_cable",
                        name=f"Copper network cable {marker}",
                        attributes={
                            "connector_a": "RJ45",
                            "connector_b": "RJ45",
                            "length_m": "2.5",
                            "cable_category": "Cat 5e",
                            "shielding": "UTP",
                        },
                    ),
                )
                nic_id = await create_item(
                    db,
                    ItemCreate(
                        category_key="nic",
                        manufacturer_id=manufacturer.id,
                        name=f"NIC {marker}",
                        attributes={
                            "port_count": 2,
                            "port_speed_mbps": 25000,
                            "media_type": "SFP28",
                            "protocol": "Ethernet",
                            "bracket": "full_profile",
                            "sriov": True,
                        },
                    ),
                )
                disk_id = await create_item(
                    db,
                    ItemCreate(
                        category_key="disk",
                        manufacturer_id=manufacturer.id,
                        name=f"Disk {marker}",
                        attributes={
                            "drive_type": "SSD",
                            "capacity_bytes": 1_920_383_410_176,
                            "form_factor": "2.5",
                            "interface": "SAS",
                            "interface_speed_mbps": 12000,
                        },
                    ),
                )

                sfp = await get_item_record(db, sfp_id)
                optics = await get_item_record(db, optics_id)
                power = await get_item_record(db, power_id)
                copper = await get_item_record(db, copper_id)
                nic = await get_item_record(db, nic_id)
                disk = await get_item_record(db, disk_id)

                assert sfp.item.accounting_mode == AccountingMode.QUANTITY
                assert optics.item.accounting_mode == AccountingMode.QUANTITY
                assert power.item.accounting_mode == AccountingMode.QUANTITY
                assert copper.item.accounting_mode == AccountingMode.QUANTITY
                assert nic.item.accounting_mode == AccountingMode.SERIAL
                assert disk.item.accounting_mode == AccountingMode.SERIAL
                assert sfp.attributes["tx_wavelength_nm"] == Decimal("1310.125")
                assert optics.attributes["length_m"] == Decimal("2.500")
                assert copper.attributes["length_m"] == Decimal("2.5")
                assert disk.attributes["capacity_bytes"] == 1_920_383_410_176

                await update_item(
                    db,
                    sfp_id,
                    ItemPatch(
                        name=f"Updated SFP {marker}",
                        attributes={
                            "speed_mbps": 25000,
                            "dom_ddm": False,
                        },
                    ),
                    fields_set={"name", "attributes"},
                )
                updated = await get_item_record(db, sfp_id)
                assert updated.item.name == f"Updated SFP {marker}"
                assert updated.attributes == {
                    "speed_mbps": 25000,
                    "dom_ddm": False,
                }

                with pytest.raises(CatalogValidationError) as immutable:
                    await update_item(
                        db,
                        sfp_id,
                        ItemPatch(category_key="disk"),
                        fields_set={"category_key"},
                    )
                assert immutable.value.code == "category_immutable"

                with pytest.raises(CatalogValidationError) as accounting:
                    await update_item(
                        db,
                        sfp_id,
                        ItemPatch(accounting_mode=AccountingMode.SERIAL),
                        fields_set={"accounting_mode"},
                    )
                assert accounting.value.code == "accounting_mode_immutable"

                await set_item_archived(db, sfp_id, archived=True)
                archived = await get_item_record(db, sfp_id)
                assert archived.item.status == ItemStatus.ARCHIVED
                assert archived.item.archived_at is not None
                first_archived_at = archived.item.archived_at

                await set_item_archived(db, sfp_id, archived=True)
                repeated_archive = await get_item_record(db, sfp_id)
                assert repeated_archive.item.archived_at == first_archived_at

                active_page = await list_items(
                    db,
                    category_key="sfp",
                    item_status=ItemStatus.ACTIVE,
                    limit=100,
                    offset=0,
                )
                archived_page = await list_items(
                    db,
                    category_key="sfp",
                    item_status=ItemStatus.ARCHIVED,
                    limit=100,
                    offset=0,
                )
                assert sfp_id not in {record.item.id for record in active_page.items}
                assert sfp_id in {record.item.id for record in archived_page.items}

                await set_item_archived(db, sfp_id, archived=False)
                unarchived = await get_item_record(db, sfp_id)
                assert unarchived.item.status == ItemStatus.ACTIVE
                assert unarchived.item.archived_at is None
                await set_item_archived(db, sfp_id, archived=False)
                assert (await get_item_record(db, sfp_id)).item.archived_at is None

                mpn_candidates = await check_duplicate_candidates(
                    db,
                    DuplicateCheckRequest(
                        category_key="sfp",
                        manufacturer_id=manufacturer.id,
                        manufacturer_part_number="  pn-100 ",
                        name="Ignored for MPN",
                    ),
                )
                assert [candidate.item.id for candidate in mpn_candidates] == [sfp_id]
                assert (
                    mpn_candidates[0].reason
                    == "same_category_manufacturer_mpn"
                )

                other_manufacturer = await create_manufacturer(
                    db,
                    ManufacturerCreate(name=f"Other Manufacturer {marker}"),
                )
                assert (
                    await check_duplicate_candidates(
                        db,
                        DuplicateCheckRequest(
                            category_key="sfp",
                            manufacturer_id=other_manufacturer.id,
                            manufacturer_part_number="PN-100",
                            name="Ignored",
                        ),
                    )
                    == []
                )
                assert (
                    await check_duplicate_candidates(
                        db,
                        DuplicateCheckRequest(
                            category_key="optics",
                            manufacturer_id=manufacturer.id,
                            manufacturer_part_number="PN-100",
                            name="Ignored",
                        ),
                    )
                    == []
                )

                name_candidates = await check_duplicate_candidates(
                    db,
                    DuplicateCheckRequest(
                        category_key="power_cable",
                        name=f"  power   cable {marker} ",
                        model=" c13-c14 ",
                    ),
                )
                assert [candidate.item.id for candidate in name_candidates] == [
                    power_id
                ]
                assert (
                    name_candidates[0].reason
                    == "same_category_manufacturer_name_model"
                )

                before_failure = len(
                    (
                        await db.scalars(
                            select(Item.id).where(
                                Item.name == f"Invalid {marker}"
                            )
                        )
                    ).all()
                )
                with pytest.raises(CatalogValidationError):
                    await create_item(
                        db,
                        ItemCreate(
                            category_key="sfp",
                            name=f"Invalid {marker}",
                            attributes={"form_factor": "SFP+"},
                        ),
                    )
                after_failure = len(
                    (
                        await db.scalars(
                            select(Item.id).where(
                                Item.name == f"Invalid {marker}"
                            )
                        )
                    ).all()
                )
                assert before_failure == after_failure == 0
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
