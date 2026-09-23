from decimal import Decimal
from pathlib import Path
from typing import cast
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile

import pytest

from app.bootstrap.inventory_workbook import SHEETS, normalize_row, read_workbook
from app.modules.catalog.normalization import item_signature, normalize_reach


def synthetic_workbook(
    path: Path,
    *,
    invalid: bool = False,
    current_layout: bool = False,
    misplaced_splitter_header: bool = False,
) -> Path:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook = Element("workbook", xmlns=ns)
    sheets = SubElement(workbook, "sheets")
    relationships = Element("Relationships")
    with ZipFile(path, "w") as archive:
        for index, (name, headers) in enumerate(SHEETS.items(), 1):
            SubElement(
                sheets, "sheet", {"name": name, "sheetId": str(index), f"{{{rel}}}id": f"r{index}"}
            )
            SubElement(
                relationships, "Relationship", Id=f"r{index}", Target=f"worksheets/sheet{index}.xml"
            )
            sheet = Element("worksheet", xmlns=ns)
            data = SubElement(sheet, "sheetData")
            rows = [list(headers)]
            if name == "Оптические патч-корды":
                rows[0][-1] = ""  # Real format allows an explicitly mapped, unnamed H column.
                rows += [
                    ["MMF", "OM4", "LC/UPC", "LC/UPC", "5 м", "Duplex", q, c]
                    for q, c in [("4", "Blue"), ("20", " blue "), ("2", "Pearlescent")]
                ]
                if invalid:
                    rows[1][6] = "1.5"
            if current_layout and name == "Оптические сплиттеры  делители":
                rows += [
                    [
                        "Оптический сплиттер/coupler",
                        "1×2",
                        "SMF",
                        "1310/1550 нм",
                        "LC/UPC",
                        "50/50",
                        "1 COM → 2 OUT",
                        "15",
                    ],
                ]
                if misplaced_splitter_header:
                    rows[0][0] = ""
                    rows += [
                        [],
                        [],
                        ["", "", "Тип"],
                    ]
            if current_layout and name == "Ethernet патч-корды":
                rows += [
                    [
                        "Cat.5e",
                        "RJ-45",
                        "RJ-45",
                        "1,5 м",
                        "UTP",
                        "Серый",
                        "7",
                    ]
                ]
            for number, values in enumerate(rows, 1):
                row = SubElement(data, "row", r=str(number))
                for col, value in enumerate(values):
                    if value:
                        cell = SubElement(row, "c", r=f"{chr(65 + col)}{number}", t="inlineStr")
                        SubElement(SubElement(cell, "is"), "t").text = value
            archive.writestr(f"xl/worksheets/sheet{index}.xml", tostring(sheet))
        archive.writestr("xl/workbook.xml", tostring(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", tostring(relationships))
    return path


def test_read_workbook_aggregates_normalized_identity_and_optional_color(tmp_path: Path) -> None:
    result = read_workbook(synthetic_workbook(tmp_path / "synthetic.xlsx"))
    assert not result.errors
    assert len(result.sheets) == 9 and result.raw_rows == 3
    assert result.source_quantity == 26 and len(result.items) == 2
    assert sorted(item.quantity for item in result.items) == [2, 24]
    duplicates = cast(list[object], result.report()["duplicates"])
    assert len(duplicates) == 1
    assert any("column H" in warning for warning in result.warnings)


def test_fractional_quantity_and_missing_workbook_fail(tmp_path: Path) -> None:
    assert read_workbook(synthetic_workbook(tmp_path / "invalid.xlsx", invalid=True)).errors
    assert read_workbook(tmp_path / "missing.xlsx").errors == [
        "DATA_IMPORT_BLOCKED_SOURCE_FILE_MISSING"
    ]


def test_explicit_drive_type_overrides_sheet_label() -> None:
    row = dict(
        zip(
            SHEETS["SSD  Накопители"],
            [
                "Synthetic",
                "Synthetic HDD",
                "2.5",
                "SAS",
                "1 ТБ",
                "6 Гбит/с",
                "10 000 RPM",
                "Enterprise HDD",
                "2",
            ],
            strict=True,
        )
    )
    item = normalize_row("SSD  Накопители", row, "synthetic")
    assert item.category == "hdd"
    assert item.attributes["interface_speed"] == "6 Гбит/с"
    assert item.attributes["rpm"] == 10000


def test_ethernet_patch_cord_normalization() -> None:
    row = dict(
        zip(
            SHEETS["Ethernet патч-корды"],
            [
                "Cat.5e",
                "RJ-45",
                "RJ-45",
                "1,5 м",
                "UTP",
                "Серый",
                "7",
            ],
            strict=True,
        )
    )

    item = normalize_row(
        "Ethernet патч-корды",
        row,
        "synthetic",
    )

    assert item.category == "ethernet_patch_cord"
    assert item.manufacturer is None
    assert item.model is None
    assert item.quantity == 7
    assert item.attributes == {
        "cable_category": "Cat.5e",
        "connector_a": "RJ-45",
        "connector_b": "RJ-45",
        "length_m": Decimal("1.5"),
        "shielding": "UTP",
        "color": "Серый",
    }
    assert "Cat.5e" in item.name
    assert "1.5 м" in item.name


def test_current_workbook_layout_is_accepted(
    tmp_path: Path,
) -> None:
    result = read_workbook(
        synthetic_workbook(
            tmp_path / "current-layout.xlsx",
            current_layout=True,
        )
    )

    assert not result.errors
    assert result.raw_rows == 5
    assert result.source_quantity == 48
    assert len(result.items) == 4
    assert {
        item.category
        for item in result.items
    } >= {
        "ethernet_patch_cord",
        "optical_splitter",
    }


def test_misplaced_splitter_header_is_rejected(
    tmp_path: Path,
) -> None:
    result = read_workbook(
        synthetic_workbook(
            tmp_path / "misplaced-splitter-header.xlsx",
            current_layout=True,
            misplaced_splitter_header=True,
        )
    )

    assert any(
        "Оптические сплиттеры  делители: headers differ"
        in error
        for error in result.errors
    )


def test_zero_quantity_requires_explicit_import_opt_in() -> None:
    row = dict(
        zip(
            SHEETS["Ethernet патч-корды"],
            [
                "Cat.5e",
                "RJ-45",
                "RJ-45",
                "1 м",
                "UTP",
                "Серый",
                "0",
            ],
            strict=True,
        )
    )

    with pytest.raises(
        ValueError,
        match="quantity must be a positive integer",
    ):
        normalize_row(
            "Ethernet патч-корды",
            row,
            "synthetic",
        )

    item = normalize_row(
        "Ethernet патч-корды",
        row,
        "synthetic",
        allow_zero_quantity=True,
    )

    assert item.quantity == 0


def test_drive_column_misalignment_is_rejected() -> None:
    row = dict(
        zip(
            SHEETS["SSD  Накопители"],
            [
                "Seagate",
                "Exos 7E10 ST4000NM025B",
                "4 ТБ",
                "3.5″",
                "SAS",
                "12 Гбит/с",
                "7 200 RPM",
                "Enterprise HDD",
                "2",
            ],
            strict=True,
        )
    )

    with pytest.raises(
        ValueError,
        match="unsupported drive form factor",
    ):
        normalize_row(
            "SSD  Накопители",
            row,
            "synthetic",
        )


def test_ssd_requires_rotation_placeholder() -> None:
    row = dict(
        zip(
            SHEETS["SSD  Накопители"],
            [
                "Micron",
                "5300 PRO",
                "2.5″",
                "SATA",
                "480 ГБ",
                "6 Гбит/с",
                "7200 RPM",
                "Enterprise SSD",
                "1",
            ],
            strict=True,
        )
    )

    with pytest.raises(
        ValueError,
        match="SSD rotation speed must be empty marker",
    ):
        normalize_row(
            "SSD  Накопители",
            row,
            "synthetic",
        )


@pytest.mark.parametrize(
    "reach,expected",
    [
        ("до 2 км", 2000),
        ("до 300 м", 300),
        ("OM3: до 100 м\nOM4: до 125 м", 125),
        ("до 0,5 км", 500),
    ],
)
def test_reach_normalization(reach: str, expected: int) -> None:
    assert normalize_reach(reach) == expected


@pytest.mark.parametrize("reach", ["unknown", "до 10 км possibly 40", "0 м", "10/20 км"])
def test_ambiguous_reach_fails(reach: str) -> None:
    with pytest.raises(ValueError):
        normalize_reach(reach)


def test_decimal_and_color_identity_normalization() -> None:
    assert item_signature(
        "optical_patch_cord", None, None, {"length_m": Decimal("5.00"), "color": " Blue "}
    ) == item_signature(
        "optical_patch_cord", None, None, {"length_m": Decimal("5"), "color": "blue"}
    )


@pytest.mark.asyncio
async def test_bootstrap_requires_existing_location_and_refuses_second_import(
    migration_database: str,
    tmp_path: Path,
) -> None:
    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.bootstrap.inventory_workbook import import_inventory
    from app.modules.catalog.models import Item
    from app.modules.inventory.models import Movement, StockBalance
    from app.modules.inventory.schemas import LocationCreate
    from app.modules.inventory.service import create_location
    from tests.migration_helpers import alembic
    from tests.warehouse_helpers import actor

    url = migration_database
    alembic(url, "upgrade", "head")
    engine = create_async_engine(url)
    validation = read_workbook(synthetic_workbook(tmp_path / "synthetic.xlsx"))
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            user, _ = await actor(db)
            with pytest.raises(ValueError, match="existing active target"):
                await import_inventory(db, validation, target="missing", actor_user_id=user.id)
            assert await db.scalar(select(func.count()).select_from(Item)) == 0
            await create_location(
                db, LocationCreate(code="synthetic", name="Synthetic", location_type="WAREHOUSE")
            )
            await import_inventory(db, validation, target="synthetic", actor_user_id=user.id)
            await db.commit()
            assert await db.scalar(select(func.count()).select_from(Item)) == 2
            assert await db.scalar(select(func.sum(StockBalance.quantity))) == 26
            assert await db.scalar(select(func.count()).select_from(Movement)) == 1
            assert await db.scalar(select(Movement.movement_type)) == "RECEIPT"
            with pytest.raises(ValueError, match="BOOTSTRAP_ALREADY_POPULATED"):
                await import_inventory(db, validation, target="synthetic", actor_user_id=user.id)
            sql = (
                Path(__file__).parents[1] / "scripts/reconcile_inventory_projections.sql"
            ).read_text()
            assert not (await db.execute(text(sql))).all()
    finally:
        await engine.dispose()


def test_production_bootstrap_runtime_guard_is_fail_closed() -> None:
    from app.bootstrap.production_inventory import assert_production_runtime

    assert_production_runtime(
        app_env="production",
        database_url="postgresql+asyncpg://runtime:secret@postgres:5432/inventory",
        gate_enabled=False,
    )

    with pytest.raises(ValueError, match="APP_ENV=production"):
        assert_production_runtime(
            app_env="test",
            database_url="postgresql+asyncpg://runtime:secret@postgres:5432/inventory",
            gate_enabled=False,
        )

    with pytest.raises(ValueError, match="production Docker PostgreSQL boundary"):
        assert_production_runtime(
            app_env="production",
            database_url="postgresql+asyncpg://runtime:secret@localhost:5432/inventory",
            gate_enabled=False,
        )

    with pytest.raises(ValueError, match="must remain false"):
        assert_production_runtime(
            app_env="production",
            database_url="postgresql+asyncpg://runtime:secret@postgres:5432/inventory",
            gate_enabled=True,
        )


def test_production_bootstrap_validation_contract(tmp_path: Path) -> None:
    from app.bootstrap.production_inventory import assert_validation_contract

    validation = read_workbook(synthetic_workbook(tmp_path / "synthetic-production.xlsx"))

    assert_validation_contract(
        validation,
        expected_rows=3,
        expected_items=2,
        expected_quantity=26,
    )

    with pytest.raises(ValueError, match="normalized item count"):
        assert_validation_contract(
            validation,
            expected_rows=3,
            expected_items=3,
            expected_quantity=26,
        )


@pytest.mark.asyncio
async def test_production_bootstrap_creates_single_location_and_receipt(
    migration_database: str,
    tmp_path: Path,
) -> None:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.bootstrap.production_inventory import bootstrap_transaction
    from app.modules.catalog.models import Item
    from app.modules.inventory.enums import LocationType
    from app.modules.inventory.models import Location, Movement, MovementLine, StockBalance
    from tests.migration_helpers import alembic
    from tests.warehouse_helpers import actor

    alembic(migration_database, "upgrade", "head")

    engine = create_async_engine(migration_database)
    validation = read_workbook(
        synthetic_workbook(tmp_path / "synthetic-production-bootstrap.xlsx")
    )

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            user, _ = await actor(db)

            result = await bootstrap_transaction(
                db,
                validation,
                location_code="SYNTHETIC-01",
                location_name="Synthetic warehouse",
                location_type=LocationType.WAREHOUSE,
                actor_user_id=user.id,
                expected_items=2,
                expected_quantity=26,
            )

            await db.commit()

            assert result["projection_drift_rows"] == 0
            assert result["stock_quantity"] == 26

            assert await db.scalar(
                select(func.count()).select_from(Location)
            ) == 1

            assert await db.scalar(
                select(func.count()).select_from(Item)
            ) == 2

            assert await db.scalar(
                select(func.count()).select_from(Movement)
            ) == 1

            assert await db.scalar(
                select(func.count()).select_from(MovementLine)
            ) == 2

            assert await db.scalar(
                select(func.sum(StockBalance.quantity))
            ) == 26

            with pytest.raises(ValueError, match="BOOTSTRAP_ALREADY_POPULATED"):
                await bootstrap_transaction(
                    db,
                    validation,
                    location_code="SYNTHETIC-02",
                    location_name="Second synthetic warehouse",
                    location_type=LocationType.WAREHOUSE,
                    actor_user_id=user.id,
                    expected_items=2,
                    expected_quantity=26,
                )

            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("limit", ["MAX_WORKBOOK_BYTES", "MAX_ARCHIVE_MEMBERS",
                                  "MAX_UNCOMPRESSED_BYTES", "MAX_XML_BYTES",
                                  "MAX_XML_NODES", "MAX_XML_DEPTH"])
def test_workbook_resource_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    from app.bootstrap import inventory_workbook

    path = synthetic_workbook(tmp_path / "synthetic.xlsx")
    monkeypatch.setattr(inventory_workbook, limit, 1)
    assert any("resource limit" in error for error in read_workbook(path).errors)


def test_workbook_rejects_doctype_including_utf16(tmp_path: Path) -> None:
    for encoding in ("utf-8", "utf-16"):
        path = tmp_path / f"doctype-{encoding}.xlsx"
        with ZipFile(path, "w") as archive:
            archive.writestr("xl/_rels/workbook.xml.rels", (
                f'<?xml version="1.0" encoding="{encoding}"?>'
                '<!DOCTYPE r [<!ENTITY x "payload">]><r>&x;</r>'
            ).encode(encoding))
        assert any("document types" in error for error in read_workbook(path).errors)


def test_workbook_rejects_duplicate_members(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", "<r/>")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("xl/workbook.xml", "<other/>")
    assert any("duplicate ZIP" in error for error in read_workbook(path).errors)
