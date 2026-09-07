from decimal import Decimal
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile

import pytest

from app.bootstrap.inventory_workbook import SHEETS, normalize_row, read_workbook
from app.modules.catalog.normalization import item_signature, normalize_reach


def synthetic_workbook(path: Path, *, invalid=False):
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


def test_read_workbook_aggregates_normalized_identity_and_optional_color(tmp_path):
    result = read_workbook(synthetic_workbook(tmp_path / "synthetic.xlsx"))
    assert not result.errors
    assert len(result.sheets) == 8 and result.raw_rows == 3
    assert result.source_quantity == 26 and len(result.items) == 2
    assert sorted(item.quantity for item in result.items) == [2, 24]
    assert len(result.report()["duplicates"]) == 1
    assert any("column H" in warning for warning in result.warnings)


def test_fractional_quantity_and_missing_workbook_fail(tmp_path):
    assert read_workbook(synthetic_workbook(tmp_path / "invalid.xlsx", invalid=True)).errors
    assert read_workbook(tmp_path / "missing.xlsx").errors == [
        "DATA_IMPORT_BLOCKED_SOURCE_FILE_MISSING"
    ]


def test_explicit_drive_type_overrides_sheet_label():
    row = dict(
        zip(
            SHEETS["SSD  Накопители"],
            [
                "Synthetic",
                "Synthetic HDD",
                "2.5",
                "SAS",
                "1 TB",
                "10 000 RPM",
                "Enterprise HDD",
                "2",
            ],
            strict=True,
        )
    )
    item = normalize_row("SSD  Накопители", row, "synthetic")
    assert item.category == "hdd" and item.attributes["rpm"] == 10000


@pytest.mark.parametrize(
    "reach,expected",
    [
        ("до 2 км", 2000),
        ("до 300 м", 300),
        ("OM3: до 100 м\nOM4: до 125 м", 125),
        ("до 0,5 км", 500),
    ],
)
def test_reach_normalization(reach, expected):
    assert normalize_reach(reach) == expected


@pytest.mark.parametrize("reach", ["unknown", "до 10 км possibly 40", "0 м", "10/20 км"])
def test_ambiguous_reach_fails(reach):
    with pytest.raises(ValueError):
        normalize_reach(reach)


def test_decimal_and_color_identity_normalization():
    assert item_signature(
        "optical_patch_cord", None, None, {"length_m": Decimal("5.00"), "color": " Blue "}
    ) == item_signature(
        "optical_patch_cord", None, None, {"length_m": Decimal("5"), "color": "blue"}
    )


@pytest.mark.asyncio
async def test_bootstrap_requires_existing_location_and_refuses_second_import(
    migration_database, tmp_path
):
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
