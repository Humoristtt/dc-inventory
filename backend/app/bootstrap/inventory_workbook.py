"""Validate external inventory.xlsx; bootstrap an empty LOCAL catalog and journal.

No spreadsheet library or workbook copy is needed: the input is read-only OOXML.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import posixpath
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.configuration import LEAVES
from app.modules.catalog.normalization import (
    clean_text,
    identity_text,
    item_signature,
    normalize_reach,
)
from app.modules.catalog.schemas import ItemCreate, ManufacturerCreate
from app.modules.catalog.service import create_item, create_manufacturer
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User
from app.modules.inventory.enums import LocationStatus, MovementType
from app.modules.inventory.models import Location, Movement
from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
from app.modules.inventory.service import create_movement

SOURCE = Path.home() / "dc-inventory-input" / "inventory.xlsx"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SHEETS: dict[str, tuple[str, ...]] = {
    "SFP модули": (
        "Производитель",
        "Модель",
        "Скорость",
        "Длина волны",
        "Дальность",
        "Форм-фактор",
        "Волокно",
        "Разъём",
        "Количество",
    ),
    "Контроллеры и PCIe-адаптеры": (
        "Производитель",
        "Модель",
        "Интерфейс",
        "Порты",
        "Назначение",
        "Особенности",
        "Количество",
    ),
    "Сетевые карты": (
        "Производитель",
        "Модель",
        "Интерфейс",
        "Порты",
        "Скорость",
        "Тип портов",
        "Назначение",
        "Количество",
    ),
    "SSD  Накопители": (
        "Производитель",
        "Модель",
        "Форм-фактор",
        "Интерфейс",
        "Объём",
        "Скорость интерфейса",
        "Тип",
        "Количество",
    ),
    "Оптические патч-корды": (
        "Тип волокна",
        "Категория",
        "Разъём A",
        "Разъём B",
        "Длина",
        "Исполнение",
        "Количество",
        "Цвет",
    ),
    "Оперативная память (RAM)": (
        "Производитель",
        "Модель",
        "Объём",
        "Тип",
        "Скорость",
        "Организация",
        "ECC",
        "Количество",
    ),
    "Кабели питания": ("Тип", "Разъём A", "Разъём B", "Длина", "Номинал", "Цвет", "Количество"),
    "Оптические сплиттеры  делители": (
        "Тип",
        "Конфигурация",
        "Волокно",
        "Рабочие длины волн",
        "Разъёмы",
        "Деление",
        "Исполнение",
        "Количество",
    ),
}


@dataclass
class Equipment:
    category: str
    manufacturer: str | None
    model: str | None
    attributes: dict[str, str | int | Decimal | bool]
    quantity: int
    signature: str
    sources: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        keys: tuple[str, ...]
        if self.model:
            return f"{self.manufacturer} {self.model}" if self.manufacturer else self.model
        if self.category == "optical_patch_cord":
            keys = (
                "fiber_category",
                "connector_a",
                "connector_b",
                "length_m",
                "construction",
                "color",
            )
        elif self.category == "power_cable":
            keys = ("type", "connector_a", "connector_b", "length_m", "color")
        else:
            keys = ("type", "configuration", "connector", "split_ratio")
        return " · ".join(
            f"{self.attributes[key]}{' м' if key == 'length_m' else ''}"
            for key in keys
            if key in self.attributes
        )


@dataclass
class Validation:
    path: Path
    sheets: list[str] = field(default_factory=list)
    raw_rows: int = 0
    source_quantity: int = 0
    items: list[Equipment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def report(self) -> dict[str, object]:
        counts = Counter(x.category for x in self.items)
        quantities: Counter[str] = Counter()
        for item in self.items:
            quantities[item.category] += item.quantity
        return {
            "workbook_path": str(self.path),
            "sheets_found": self.sheets,
            "raw_rows": self.raw_rows,
            "total_source_quantity": self.source_quantity,
            "normalized_unique_items": len(self.items),
            "duplicates": [
                {
                    "category": x.category,
                    "sources": x.sources,
                    "quantity": x.quantity,
                    "signature": x.signature,
                }
                for x in self.items
                if len(x.sources) > 1
            ],
            "leaf_categories": {
                key: {"items": counts[key], "quantity": quantities[key]} for key in sorted(LEAVES)
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "valid": not self.errors,
        }


def _positive_integer(value: str) -> int:
    number = Decimal(value)
    if (
        not number.is_finite()
        or number != number.to_integral_value()
        or not 0 < number <= 2**53 - 1
    ):
        raise ValueError("quantity must be a positive integer within the supported range")
    return int(number)


def normalize_row(sheet: str, row: dict[str, str], source: str) -> Equipment:
    keys: tuple[str, ...]
    manufacturer, model = row.get("Производитель"), row.get("Модель")
    if sheet == "SFP модули":
        speed = row["Скорость"]
        if not re.fullmatch(r"[\d,./]+\s*(?:Гбит/с|Мбит/с|G FC)", speed):
            raise ValueError("unsupported transceiver speed/protocol")
        category = "transceiver_fc" if speed.endswith("G FC") else "transceiver_ethernet"
        keys = ("speed", "wavelength", "reach", "form_factor", "fiber", "connector")
    elif sheet == "Сетевые карты":
        application = row["Назначение"]
        if application.startswith("Fibre Channel HBA"):
            category = "network_fc"
        elif application == "Ethernet NIC":
            category = "network_ethernet"
        else:
            raise ValueError("unknown network adapter category")
        keys = ("interface", "ports", "speed", "port_type", "application")
    elif sheet == "SSD  Накопители":
        if row["Тип"] not in {"Enterprise SSD", "Enterprise HDD"}:
            raise ValueError("unknown drive type")
        category = "ssd" if row["Тип"] == "Enterprise SSD" else "hdd"
        keys = (
            "form_factor",
            "interface",
            "capacity",
            "interface_speed" if category == "ssd" else "rpm",
            "type",
        )
    else:
        category = {
            "Контроллеры и PCIe-адаптеры": "pcie_adapter",
            "Оптические патч-корды": "optical_patch_cord",
            "Оперативная память (RAM)": "ram",
            "Кабели питания": "power_cable",
            "Оптические сплиттеры  делители": "optical_splitter",
        }[sheet]
        keys = tuple(a.key for a in LEAVES[category][2])
    headers = [h for h in SHEETS[sheet] if h not in {"Производитель", "Модель", "Количество"}]
    attributes: dict[str, str | int | Decimal | bool] = {}
    for key, header in zip(keys, headers, strict=True):
        value = row.get(header, "")
        if not value and key == "color" and category == "optical_patch_cord":
            continue
        if key == "length_m":
            match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*м", value)
            if not match:
                raise ValueError("unsupported cable length")
            length = Decimal(match[1].replace(",", "."))
            if length <= 0:
                raise ValueError("cable length must be positive")
            attributes[key] = length
        elif key == "ports" and category.startswith("network_"):
            attributes[key] = _positive_integer(value)
        elif key == "rpm":
            match = re.fullmatch(r"([\d ]+) RPM", value)
            if not match:
                raise ValueError("HDD speed must be RPM")
            attributes[key] = _positive_integer(match[1].replace(" ", ""))
        elif key == "ecc":
            if value not in {"Да", "Нет"}:
                raise ValueError("ECC must be Да or Нет")
            attributes[key] = value == "Да"
        else:
            attributes[key] = value
    if category.startswith("transceiver_"):
        attributes["reach_m"] = normalize_reach(str(attributes["reach"]))
    return Equipment(
        category,
        manufacturer,
        model,
        attributes,
        _positive_integer(row["Количество"]),
        item_signature(category, manufacturer, model, attributes),
        [source],
    )


def read_workbook(path: Path = SOURCE) -> Validation:
    result = Validation(path.expanduser().resolve())
    if not path.exists():
        result.errors.append("DATA_IMPORT_BLOCKED_SOURCE_FILE_MISSING")
        return result
    grouped: dict[str, Equipment] = {}
    try:
        with ZipFile(path) as archive:
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = [
                    "".join(node.itertext())
                    for node in ET.fromstring(archive.read("xl/sharedStrings.xml"))
                ]
            relationships = {
                node.attrib["Id"]: node.attrib["Target"]
                for node in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            }
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            for sheet in workbook.findall("s:sheets/s:sheet", NS):
                name = sheet.attrib["name"]
                result.sheets.append(name)
                if name not in SHEETS:
                    result.errors.append(f"unknown worksheet: {name}")
                    continue
                relation = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                target = relationships[relation]
                member = (
                    target.lstrip("/")
                    if target.startswith("/")
                    else posixpath.normpath("xl/" + target)
                )
                root = ET.fromstring(archive.read(member))
                rows: list[tuple[int, dict[int, str]]] = []
                for xml_row in root.findall("s:sheetData/s:row", NS):
                    cells = {}
                    for cell in xml_row.findall("s:c", NS):
                        ref = cell.attrib["r"]
                        if cell.find("s:f", NS) is not None:
                            result.errors.append(f"{name}!{ref}: formulas are not supported")
                        col = 0
                        for char in re.match(r"[A-Z]+", ref)[0]:  # type: ignore[index]
                            col = col * 26 + ord(char) - 64
                        value = cell.find("s:v", NS)
                        text = value.text or "" if value is not None else ""
                        if cell.get("t") == "s":
                            text = strings[int(text)]
                        elif cell.get("t") == "inlineStr":
                            text = "".join(cell.find("s:is", NS).itertext())  # type: ignore[union-attr]
                        if text.strip():
                            cells[col] = clean_text(text)
                    if cells:
                        rows.append((int(xml_row.attrib["r"]), cells))
                headers = SHEETS[name]
                header = rows[0][1] if rows and rows[0][0] == 1 else {}
                if name == "Оптические патч-корды" and 8 not in header:
                    header[8] = "Цвет"
                    result.warnings.append(
                        f"{name}!H1: missing optional Цвет header; explicitly mapped column H"
                    )
                expected = dict(enumerate(headers, 1))
                if header != expected:
                    result.errors.append(
                        f"{name}: headers differ; expected {list(headers)}, found {header}"
                    )
                    continue
                for number, cells in rows[1:]:
                    source = f"{name}!{number}"
                    result.raw_rows += 1
                    row = {label: cells.get(index, "") for index, label in expected.items()}
                    try:
                        result.source_quantity += _positive_integer(row["Количество"])
                        if set(cells) - set(expected):
                            raise ValueError("unmapped nonempty columns")
                        missing = [
                            h
                            for h, value in row.items()
                            if not value and not (name == "Оптические патч-корды" and h == "Цвет")
                        ]
                        if missing:
                            raise ValueError(f"blank required fields: {missing}")
                        item = normalize_row(name, row, source)
                        if item.signature in grouped:
                            grouped[item.signature].quantity += item.quantity
                            grouped[item.signature].sources.append(source)
                        else:
                            grouped[item.signature] = item
                    except (ValueError, InvalidOperation) as error:
                        result.errors.append(f"{source}: {error}")
            for missing_sheet in sorted(set(SHEETS) - set(result.sheets)):
                result.errors.append(f"missing worksheet: {missing_sheet}")
    except (BadZipFile, ET.ParseError, KeyError, OSError) as error:
        result.errors.append(f"invalid workbook: {error}")
    result.items = sorted(grouped.values(), key=lambda x: (x.category, x.signature))
    for key, actual, expected_total in (
        ("raw_rows", result.raw_rows, 78),
        ("source_quantity", result.source_quantity, 670),
    ):
        if actual != expected_total:
            result.warnings.append(f"{key}: expected {expected_total}, actual {actual}")
    return result


async def import_inventory(
    db: AsyncSession, validation: Validation, *, target: str, actor_user_id: UUID
) -> UUID:
    from app.modules.catalog.models import Item, Manufacturer

    if validation.errors or not validation.items:
        raise ValueError("workbook validation failed")
    await db.execute(select(func.pg_advisory_xact_lock(80901620260907)))
    # This is a bootstrap, not an incremental synchronizer. Refuse any populated
    # catalog/journal, even on reruns by a different actor or with an edited file.
    if await db.scalar(select(Item.id).limit(1)) or await db.scalar(select(Movement.id).limit(1)):
        raise ValueError("BOOTSTRAP_ALREADY_POPULATED: requires empty catalog and movement journal")
    location = await db.scalar(
        select(Location).where(or_(Location.code == target, cast(Location.id, String) == target))
    )
    if location is None or location.status != LocationStatus.ACTIVE:
        raise ValueError("explicit existing active target location required")
    actor = await db.get(User, actor_user_id)
    if (
        actor is None
        or actor.role != UserRole.ADMIN
        or actor.access_status != UserAccessStatus.APPROVED
    ):
        raise ValueError("existing approved administrator required")
    lines = []
    for item in validation.items:
        manufacturer = None
        if item.manufacturer:
            manufacturer = await db.scalar(select(Manufacturer).where(
                Manufacturer.normalized_name == identity_text(item.manufacturer)))
            if manufacturer is None:
                manufacturer = await create_manufacturer(
                    db,
                    ManufacturerCreate(name=item.manufacturer),
                )
        item_id = await create_item(
            db,
            ItemCreate(
                category_key=item.category,
                manufacturer_id=manufacturer.id if manufacturer else None,
                name=item.name,
                model=item.model,
                attributes=item.attributes,
            ),
        )
        lines.append(MovementLineCreate(item_id=item_id, quantity=item.quantity))
    movement = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=location.id,
            client_request_id="inventory-workbook-bootstrap-v2",
            lines=lines,
        ),
        actor_user_id=actor_user_id,
        actor_display_name="Администратор · импорт inventory.xlsx",
    )
    return movement.record.movement.id


async def _import_local(args: argparse.Namespace, validation: Validation) -> str:
    from app.core.config import get_settings

    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.app_env != "test" or url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("import requires APP_ENV=test and a loopback disposable database")
    if settings.real_inventory_mutations_enabled:
        raise ValueError("REAL_INVENTORY_MUTATIONS_ENABLED must remain false")
    engine = create_async_engine(settings.database_url)
    try:
        async with AsyncSession(engine) as db, db.begin():
            return str(
                await import_inventory(
                    db, validation, target=args.location, actor_user_id=UUID(args.actor)
                )
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--import-local", action="store_true")
    parser.add_argument("--location", help="existing location code or UUID")
    parser.add_argument("--actor", help="existing approved ADMIN UUID")
    args = parser.parse_args()
    validation = read_workbook(args.source)
    report = validation.report()
    if args.import_local:
        if not args.location or not args.actor:
            parser.error("--import-local requires --location and --actor")
        try:
            report["receipt_movement_id"] = asyncio.run(_import_local(args, validation))
        except ValueError as error:
            validation.errors.append(str(error))
            report = validation.report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(1 if validation.errors else 0)


if __name__ == "__main__":
    main()
