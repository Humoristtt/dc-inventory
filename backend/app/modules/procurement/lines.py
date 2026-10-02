from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.item_validation import load_item_create_validation_context
from app.modules.catalog.models import Item
from app.modules.catalog.read_service import load_attributes_for_items
from app.modules.catalog.schemas import ItemCreate
from app.modules.procurement.domain import (
    MAX_AGGREGATED_ITEM_QUANTITY,
    ProcurementConflictError,
    ProcurementValidationError,
)
from app.modules.procurement.models import (
    ProcurementRevisionLine,
)
from app.modules.procurement.schemas import (
    ExistingItemLineCreate,
    ProcurementLineCreate,
    ProposedItemLineCreate,
)


async def _prepare_lines(
    db: AsyncSession,
    payloads: Sequence[ProcurementLineCreate],
    revision_id: uuid.UUID,
) -> list[ProcurementRevisionLine]:
    cp04_existing_item_ids = sorted(
        {
            source_line.item_id
            for source_line in payloads
            if isinstance(
                source_line,
                ExistingItemLineCreate,
            )
        },
        key=str,
    )

    cp04_locked_items: dict[uuid.UUID, Item] = {}

    if cp04_existing_item_ids:
        cp04_locked_rows = list(
            (
                await db.scalars(
                    select(Item)
                    .where(Item.id.in_(cp04_existing_item_ids))
                    .options(joinedload(Item.category), joinedload(Item.manufacturer))
                    .order_by(Item.id)
                    .with_for_update(of=Item)
                )
            ).all()
        )
        cp04_locked_items = {item.id: item for item in cp04_locked_rows}

    existing_attributes = await load_attributes_for_items(
        db,
        [item.id for item in cp04_locked_items.values()],
    )
    proposed_payloads = [
        ItemCreate(
            category_key=payload.category_key,
            manufacturer_id=payload.manufacturer_id,
            name=payload.name,
            model=payload.model,
            attributes=payload.attributes,
        )
        for payload in payloads
        if isinstance(payload, ProposedItemLineCreate)
    ]
    proposed_validation = await load_item_create_validation_context(db, proposed_payloads)

    rows: list[ProcurementRevisionLine] = []
    proposed_index = 0
    for line_no, payload in enumerate(payloads, 1):
        snapshot: dict[str, object]
        catalog_item_id: uuid.UUID | None
        expected_identity_signature: str
        if isinstance(payload, ExistingItemLineCreate):
            item = cp04_locked_items.get(payload.item_id)
            if item is None:
                raise ProcurementConflictError(
                    "catalog item not found",
                    code="catalog_item_not_found",
                )
            if item.status != ItemStatus.ACTIVE:
                raise ProcurementConflictError(
                    "archived item cannot be procured", code="catalog_item_archived"
                )
            snapshot = {
                "category_key": item.category.key,
                "category_name": item.category.display_name,
                "manufacturer_id": (
                    str(item.manufacturer.id) if item.manufacturer is not None else None
                ),
                "manufacturer_name": (
                    item.manufacturer.name if item.manufacturer is not None else None
                ),
                "name": item.name,
                "model": item.model,
                "attributes": {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in existing_attributes[item.id].items()
                },
            }
            catalog_item_id = item.id
            expected_identity_signature = item.identity_signature
        elif isinstance(payload, ProposedItemLineCreate):
            validated = proposed_validation.validate(proposed_payloads[proposed_index])
            proposed_index += 1
            snapshot = {
                "category_key": validated.category.key,
                "category_name": validated.category.display_name,
                "manufacturer_id": (
                    str(validated.manufacturer.id) if validated.manufacturer is not None else None
                ),
                "manufacturer_name": (
                    validated.manufacturer.name if validated.manufacturer is not None else None
                ),
                "name": validated.name,
                "model": validated.model,
                "attributes": {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in validated.attributes.items()
                },
            }
            catalog_item_id = None
            expected_identity_signature = validated.identity_signature
        else:  # pragma: no cover - discriminated schema closes this branch
            raise ProcurementValidationError("unsupported procurement line")
        rows.append(
            ProcurementRevisionLine(
                id=uuid.uuid4(),
                revision_id=revision_id,
                line_no=line_no,
                line_type=payload.line_type,
                catalog_item_id=catalog_item_id,
                display_snapshot=snapshot,
                expected_identity_signature=expected_identity_signature,
                quantity=payload.quantity,
            )
        )

    _validate_aggregated_item_quantities(rows)
    return rows


def _bound_item_id(line: ProcurementRevisionLine) -> uuid.UUID | None:
    if line.catalog_item_id is not None:
        return line.catalog_item_id
    return line.binding.item_id if line.binding is not None else None


def _validate_aggregated_item_quantities(
    lines: Sequence[ProcurementRevisionLine],
    *,
    pending_line_id: uuid.UUID | None = None,
    pending_item_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, int]:
    quantities: defaultdict[uuid.UUID, int] = defaultdict(int)

    for line in lines:
        item_id = (
            pending_item_id
            if pending_line_id is not None and line.id == pending_line_id
            else _bound_item_id(line)
        )
        if item_id is None:
            continue

        quantities[item_id] += line.quantity
        if quantities[item_id] > MAX_AGGREGATED_ITEM_QUANTITY:
            raise ProcurementValidationError(
                "aggregated item quantity is too large",
                code="aggregated_item_quantity_too_large",
            )

    return dict(quantities)
