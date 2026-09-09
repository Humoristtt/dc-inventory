import uuid

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.configuration import FAMILIES, LEAVES
from app.modules.catalog.models import Category, CategoryAttribute, Item, ItemAttributeValue
from app.modules.catalog.schemas import ItemCreate, ItemPatch
from app.modules.catalog.service import (
    CatalogValidationError,
    create_item,
    get_item_record,
    set_item_archived,
    update_item,
)
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


async def test_fixed_hierarchy_and_metadata(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    categories = (await db.scalars(select(Category))).all()
    by_key = {c.key: c for c in categories}
    assert set(by_key) == set(FAMILIES) | set(LEAVES)
    for key, (parent, label, attributes) in LEAVES.items():
        assert by_key[key].parent_id == by_key[parent].id
        assert by_key[key].display_name == label
        definitions = (
            await db.scalars(
                select(CategoryAttribute).where(CategoryAttribute.category_id == by_key[key].id)
            )
        ).all()
        assert {a.key for a in definitions} == {a.key for a in attributes}
        for expected in attributes:
            actual = next(a for a in definitions if a.key == expected.key)
            assert actual.data_type.value == expected.data_type
            assert actual.required == expected.required
            assert actual.unit == expected.unit
    with pytest.raises(CatalogValidationError, match="leaf"):
        await create_item(db, ItemCreate(category_key="optics", name="invalid"))
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            db.add(
                Item(
                    category_id=by_key["optics"].id,
                    name="invalid",
                    normalized_name="invalid",
                    identity_signature=uuid.uuid4().hex * 2,
                )
            )
            await db.flush()
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(Category)
                .where(Category.key == "optical_patch_cord")
                .values(parent_id=by_key["storage"].id)
            )


async def test_identity_color_and_edit_archive_semantics(warehouse_db: AsyncSession) -> None:
    db = warehouse_db
    payload = cable_payload(color="Synthetic pearlescent " + uuid.uuid4().hex)
    item_id = await create_item(db, payload)
    duplicate = payload.model_copy(update={"name": "Different display name"})
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await create_item(db, duplicate)
    other = payload.model_copy(deep=True)
    other.attributes["color"] = "Another " + uuid.uuid4().hex
    assert await create_item(db, other) != item_id
    patch = ItemPatch(name="Renamed", attributes={**payload.attributes, "length_m": "7.5"})
    await update_item(db, item_id, patch, fields_set=patch.model_fields_set)
    record = await get_item_record(db, item_id)
    assert record.item.name == "Renamed" and str(record.attributes["length_m"]) == "7.5000000000"
    await set_item_archived(db, item_id, archived=True)
    assert (await get_item_record(db, item_id)).item.archived_at is not None
    await set_item_archived(db, item_id, archived=False)
    assert (await get_item_record(db, item_id)).item.archived_at is None
    with pytest.raises(CatalogValidationError, match="category"):
        patch = ItemPatch(category_key="power_cable")
        await update_item(db, item_id, patch, fields_set=patch.model_fields_set)


async def test_optional_blank_color_omitted_and_typed_db_constraints(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    item_id = await create_item(
        db, cable_payload(color="  ", length_m=str(uuid.uuid4().int % 100000 + 1))
    )
    assert "color" not in (await get_item_record(db, item_id)).attributes
    value = await db.scalar(
        select(ItemAttributeValue).where(
            ItemAttributeValue.item_id == item_id, ItemAttributeValue.text_value.is_not(None)
        )
    )
    assert value is not None
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ItemAttributeValue)
                .where(ItemAttributeValue.id == value.id)
                .values(integer_value=1)
            )
    other_attribute = await db.scalar(
        select(CategoryAttribute)
        .join(Category)
        .where(Category.key == "power_cable", CategoryAttribute.key == "color")
    )
    assert other_attribute is not None
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ItemAttributeValue)
                .where(ItemAttributeValue.id == value.id)
                .values(category_attribute_id=other_attribute.id)
            )


@pytest.mark.parametrize("field", ["name", "model"])
async def test_normalized_item_storage_bounds(warehouse_db: AsyncSession, field: str) -> None:
    db = warehouse_db
    payload = cable_payload()
    invalid = payload.model_copy(update={field: "ß" * 128})
    with pytest.raises(CatalogValidationError, match="normalized value exceeds"):
        await create_item(db, invalid)
    item_id = await create_item(db, payload)
    patch = ItemPatch.model_validate({field: "ß" * 128})
    with pytest.raises(CatalogValidationError, match="normalized value exceeds"):
        async with db.begin_nested():
            await update_item(db, item_id, patch, fields_set=patch.model_fields_set)
    accepted = ItemPatch.model_validate({field: "ß" * 127})
    await update_item(db, item_id, accepted, fields_set=accepted.model_fields_set)
    item = (await get_item_record(db, item_id)).item
    assert len(getattr(item, f"normalized_{field}")) == 254
