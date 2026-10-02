from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Manufacturer,
)
from app.modules.catalog.records import ValidatedItemDraft
from app.modules.catalog.schemas import ItemCreate
from app.modules.catalog.validation import (
    CatalogNotFoundError,
    CatalogValidationError,
    PreparedAttributeValue,
    _normalize_category_key,
    normalize_inline_text,
    normalize_optional_inline_text,
    validate_attribute_values,
)


@dataclass(frozen=True, slots=True)
class _PreparedItemIdentity:
    category: Category
    manufacturer: Manufacturer | None
    values: list[PreparedAttributeValue]
    identity_signature: str


@dataclass(frozen=True, slots=True)
class ItemCreateValidationContext:
    """Catalog-owned metadata used to validate one or more item drafts."""

    categories_by_key: dict[str, Category]
    manufacturers_by_id: dict[uuid.UUID, Manufacturer]
    attributes_by_category_id: dict[uuid.UUID, list[CategoryAttribute]]

    def prepare_identity(self, payload: ItemCreate) -> _PreparedItemIdentity:
        from app.modules.catalog.configuration import LEAVES, MANUFACTURED_LEAVES
        from app.modules.catalog.normalization import item_signature, normalize_reach

        normalized_key = _normalize_category_key(payload.category_key)
        category = self.categories_by_key.get(normalized_key)
        if category is None:
            raise CatalogNotFoundError("category not found")
        if category.parent_id is None or category.key not in LEAVES:
            raise CatalogValidationError(
                "leaf_category_required", "items require a fixed leaf category"
            )

        manufacturer = None
        if payload.manufacturer_id is not None:
            manufacturer = self.manufacturers_by_id.get(payload.manufacturer_id)
            if manufacturer is None:
                raise CatalogNotFoundError("manufacturer not found")
        if category.key in MANUFACTURED_LEAVES and (
            manufacturer is None or not payload.model or not payload.model.strip()
        ):
            raise CatalogValidationError("identity_required", "manufacturer and model are required")

        attributes = dict(payload.attributes)
        if category.key.startswith("transceiver_"):
            try:
                derived = normalize_reach(str(attributes.get("reach", "")))
            except ValueError as error:
                raise CatalogValidationError("reach_invalid", str(error)) from error
            if "reach_m" in attributes and attributes["reach_m"] != derived:
                raise CatalogValidationError(
                    "reach_mismatch", "normalized reach contradicts display value"
                )
            attributes["reach_m"] = derived

        values = validate_attribute_values(
            category.id,
            self.attributes_by_category_id.get(category.id, []),
            attributes,
        )
        normalized_attributes = {
            value.attribute.key: next(
                candidate
                for candidate in (
                    value.text_value,
                    value.integer_value,
                    value.decimal_value,
                    value.boolean_value,
                    value.enum_value,
                )
                if candidate is not None
            )
            for value in values
        }
        signature = item_signature(
            category.key,
            manufacturer.name if manufacturer else None,
            payload.model,
            normalized_attributes,
        )
        return _PreparedItemIdentity(
            category=category,
            manufacturer=manufacturer,
            values=values,
            identity_signature=signature,
        )

    def validate(self, payload: ItemCreate) -> ValidatedItemDraft:
        prepared = self.prepare_identity(payload)
        attributes = {
            value.attribute.key: next(
                candidate
                for candidate in (
                    value.text_value,
                    value.integer_value,
                    value.decimal_value,
                    value.boolean_value,
                    value.enum_value,
                )
                if candidate is not None
            )
            for value in prepared.values
        }
        return ValidatedItemDraft(
            category=prepared.category,
            manufacturer=prepared.manufacturer,
            name=normalize_inline_text(payload.name, field="name", max_length=255),
            model=normalize_optional_inline_text(payload.model, field="model", max_length=255),
            attributes=attributes,
            identity_signature=prepared.identity_signature,
        )


async def load_item_create_validation_context(
    db: AsyncSession,
    payloads: Sequence[ItemCreate],
) -> ItemCreateValidationContext:
    """Load shared Catalog validation metadata in bounded batch queries."""
    category_keys = sorted({_normalize_category_key(payload.category_key) for payload in payloads})
    manufacturer_ids = sorted(
        {payload.manufacturer_id for payload in payloads if payload.manufacturer_id is not None},
        key=str,
    )

    categories: list[Category] = []
    if category_keys:
        categories = list(
            (
                await db.scalars(
                    select(Category).where(Category.key.in_(category_keys)).order_by(Category.key)
                )
            ).all()
        )

    manufacturers: list[Manufacturer] = []
    if manufacturer_ids:
        manufacturers = list(
            (
                await db.scalars(
                    select(Manufacturer)
                    .where(Manufacturer.id.in_(manufacturer_ids))
                    .order_by(Manufacturer.id)
                )
            ).all()
        )

    attributes_by_category_id: dict[uuid.UUID, list[CategoryAttribute]] = {
        category.id: [] for category in categories
    }
    category_ids = sorted(attributes_by_category_id, key=str)
    if category_ids:
        definitions = (
            await db.scalars(
                select(CategoryAttribute)
                .where(CategoryAttribute.category_id.in_(category_ids))
                .order_by(
                    CategoryAttribute.category_id,
                    CategoryAttribute.sort_order,
                    CategoryAttribute.key,
                )
            )
        ).all()
        for definition in definitions:
            attributes_by_category_id[definition.category_id].append(definition)

    return ItemCreateValidationContext(
        categories_by_key={category.key: category for category in categories},
        manufacturers_by_id={manufacturer.id: manufacturer for manufacturer in manufacturers},
        attributes_by_category_id=attributes_by_category_id,
    )


async def _prepare_identity(
    db: AsyncSession, payload: ItemCreate
) -> tuple[Category, list[PreparedAttributeValue], str]:
    context = await load_item_create_validation_context(db, [payload])
    prepared = context.prepare_identity(payload)
    return prepared.category, prepared.values, prepared.identity_signature


async def validate_item_create_payload(
    db: AsyncSession,
    payload: ItemCreate,
) -> ValidatedItemDraft:
    """Validate a catalog-shaped draft without creating an Item.

    Procurement proposed lines use this public boundary so their snapshots
    obey exactly the same leaf/category/identity/attribute rules as normal
    catalog creation.
    """
    context = await load_item_create_validation_context(db, [payload])
    return context.validate(payload)
