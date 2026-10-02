from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.models import Item
from app.modules.catalog.item_validation import validate_item_create_payload
from app.modules.catalog.mutations import create_item
from app.modules.identity.policy import Capability
from app.modules.inventory.enums import MovementType
from app.modules.inventory.schemas import (
    MovementCreate,
    MovementLineCreate,
)
from app.modules.inventory.service import create_movement
from app.modules.procurement.actors import _actor_snapshot
from app.modules.procurement.domain import (
    ProcurementConflictError,
    ProcurementNotFoundError,
    ProcurementRecord,
    ProcurementValidationError,
    _normalize_comment,
)
from app.modules.procurement.enums import (
    ProcurementEventType,
    ProcurementLineType,
    ProcurementStatus,
)
from app.modules.procurement.lines import (
    _bound_item_id,
    _validate_aggregated_item_quantities,
)
from app.modules.procurement.models import (
    ProcurementLineCatalogBinding,
)
from app.modules.procurement.mutation_support import (
    _add_event,
    _lock_and_require_actor_capabilities,
    _lock_and_validate_expected,
    _require_status,
    _set_status,
)
from app.modules.procurement.notifications import (
    enqueue_procurement_notifications,
)
from app.modules.procurement.queries import get_request_record
from app.modules.procurement.schemas import (
    ExpectedStateMutation,
    LineBindingCreate,
    ProcurementAcceptanceCreate,
    ProposedItemCreateAndBind,
)


async def bind_line(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: LineBindingCreate,
    *,
    actor_user_id: uuid.UUID,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.LINE_BOUND,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_ACCEPT,),
    )

    if replay is not None:
        return record
    if record.request.status == ProcurementStatus.COMPLETED:
        raise ProcurementConflictError("completed request cannot be changed")
    line = next(
        (
            candidate
            for candidate in record.current_revision.lines
            if candidate.id == payload.line_id
        ),
        None,
    )
    if line is None:
        raise ProcurementNotFoundError("current revision line not found", code="line_not_found")
    if line.line_type != ProcurementLineType.PROPOSED_ITEM:
        raise ProcurementValidationError("existing item line is already bound")
    if line.binding is not None:
        raise ProcurementConflictError("proposed line is already bound", code="line_already_bound")
    item = await db.scalar(select(Item).where(Item.id == payload.item_id).with_for_update())
    if item is None:
        raise ProcurementNotFoundError("catalog item not found", code="catalog_item_not_found")
    if item.status != ItemStatus.ACTIVE:
        raise ProcurementConflictError(
            "archived item cannot be bound", code="catalog_item_archived"
        )
    if item.identity_signature != line.expected_identity_signature:
        raise ProcurementConflictError(
            "catalog item identity does not match approved procurement line",
            code="item_identity_mismatch",
        )

    _validate_aggregated_item_quantities(
        record.current_revision.lines,
        pending_line_id=line.id,
        pending_item_id=item.id,
    )

    db.add(
        ProcurementLineCatalogBinding(
            revision_line_id=line.id,
            item_id=item.id,
            bound_by_user_id=actor_user_id,
        )
    )
    record.request.state_version += 1
    record.request.updated_at = datetime.now(UTC)
    await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.LINE_BOUND,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        revision_id=record.request.current_revision_id,
        metadata={"line_id": str(line.id), "item_id": str(item.id)},
    )
    await db.flush()
    return await get_request_record(db, request_id)


async def create_and_bind_line(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ProposedItemCreateAndBind,
    *,
    actor_user_id: uuid.UUID,
) -> ProcurementRecord:
    """Create a proposed catalog Item and bind it in the same transaction."""
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.LINE_BOUND,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(
            Capability.PROCUREMENT_ACCEPT,
            Capability.CATALOG_MANAGE,
        ),
    )

    if replay is not None:
        return record
    if record.request.status == ProcurementStatus.COMPLETED:
        raise ProcurementConflictError("completed request cannot be changed")
    line = next(
        (
            candidate
            for candidate in record.current_revision.lines
            if candidate.id == payload.line_id
        ),
        None,
    )
    if line is None:
        raise ProcurementNotFoundError("current revision line not found", code="line_not_found")
    if line.line_type != ProcurementLineType.PROPOSED_ITEM:
        raise ProcurementValidationError("existing item line is already bound")
    if line.binding is not None:
        raise ProcurementConflictError("proposed line is already bound", code="line_already_bound")

    validated_item = await validate_item_create_payload(
        db,
        payload.item,
    )

    if validated_item.identity_signature != line.expected_identity_signature:
        raise ProcurementConflictError(
            "created catalog identity does not match approved procurement line",
            code="item_identity_mismatch",
        )

    item_id = await create_item(db, payload.item)
    db.add(
        ProcurementLineCatalogBinding(
            revision_line_id=line.id,
            item_id=item_id,
            bound_by_user_id=actor_user_id,
        )
    )
    record.request.state_version += 1
    record.request.updated_at = datetime.now(UTC)
    await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.LINE_BOUND,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        revision_id=record.request.current_revision_id,
        metadata={"line_id": str(line.id), "item_id": str(item_id), "item_created": True},
    )
    await db.flush()
    return await get_request_record(db, request_id)


async def report_discrepancy(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ExpectedStateMutation,
    *,
    comment: str,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.DISCREPANCY_REPORTED,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_ACCEPT,),
    )

    if replay is not None:
        return record
    _require_status(record.request, ProcurementStatus.AWAITING_ACCEPTANCE)
    record.request.state_version += 1
    record.request.updated_at = datetime.now(UTC)
    event = await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.DISCREPANCY_REPORTED,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        revision_id=record.request.current_revision_id,
        comment=_normalize_comment(comment, required=True),
    )
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request_id,
        request_number=record.request.request_number,
        event_id=event.id,
        action="На приёмке обнаружены расхождения.",
        lines=record.current_revision.lines,
        recipient_user_ids={record.request.assigned_manager_user_id},
    )
    await db.flush()
    return await get_request_record(db, request_id)


async def complete_acceptance(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ProcurementAcceptanceCreate,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.COMPLETED,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_ACCEPT,),
    )

    if replay is not None:
        return record
    _require_status(record.request, ProcurementStatus.AWAITING_ACCEPTANCE)
    cp04_acceptance_item_ids = sorted(
        {
            item_id
            for line in record.current_revision.lines
            if (item_id := _bound_item_id(line)) is not None
        },
        key=str,
    )

    cp04_acceptance_items: dict[
        uuid.UUID,
        Item,
    ] = {}

    if cp04_acceptance_item_ids:
        cp04_acceptance_rows = list(
            (
                await db.scalars(
                    select(Item)
                    .where(Item.id.in_(cp04_acceptance_item_ids))
                    .order_by(Item.id)
                    .with_for_update()
                )
            ).all()
        )

        cp04_acceptance_items = {item.id: item for item in cp04_acceptance_rows}

    if len(cp04_acceptance_items) != len(cp04_acceptance_item_ids):
        raise ProcurementConflictError(
            "catalog item no longer exists",
            code="catalog_item_not_found",
        )

    for line in record.current_revision.lines:
        item_id = _bound_item_id(line)

        if item_id is None:
            continue

        item = cp04_acceptance_items[item_id]

        if item.status != ItemStatus.ACTIVE:
            raise ProcurementConflictError(
                "archived item cannot be accepted",
                code="catalog_item_archived",
            )

        if item.identity_signature != line.expected_identity_signature:
            raise ProcurementConflictError(
                "catalog item identity changed after procurement approval",
                code="item_identity_mismatch",
            )

    if any(
        _bound_item_id(line) is None
        for line in record.current_revision.lines
    ):
        raise ProcurementConflictError(
            "all proposed lines must be bound", code="unbound_procurement_line"
        )

    quantities = _validate_aggregated_item_quantities(
        record.current_revision.lines
    )
    movement = await create_movement(
        db,
        MovementCreate(
            movement_type=MovementType.RECEIPT,
            destination_location_id=payload.receiving_location_id,
            client_request_id=f"procurement:{request_id}",
            lines=[
                MovementLineCreate(item_id=item_id, quantity=quantity)
                for item_id, quantity in sorted(quantities.items())
            ],
        ),
        actor_user_id=actor_user_id,
        actor_display_name=await _actor_snapshot(db, actor_user_id),
    )
    if movement.replayed:
        raise ProcurementConflictError(
            "warehouse receipt already exists for request", code="receipt_already_exists"
        )
    previous = _set_status(record.request, ProcurementStatus.COMPLETED)
    record.request.final_movement_id = movement.record.movement.id
    record.request.completed_at = datetime.now(UTC)
    event = await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.COMPLETED,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        from_status=previous,
        to_status=record.request.status,
        revision_id=record.request.current_revision_id,
        metadata={
            "movement_id": str(movement.record.movement.id),
            "receiving_location_id": str(payload.receiving_location_id),
        },
    )
    participants = {
        record.request.initiator_user_id,
        record.request.assigned_manager_user_id,
    }
    participants.update(
        event_row.actor_user_id
        for event_row in record.events
        if event_row.event_type
        in {
            ProcurementEventType.MANAGER_ACCEPTED,
            ProcurementEventType.CORRECTION_REQUESTED,
            ProcurementEventType.ASSIGNMENT_TAKEN,
            ProcurementEventType.ASSIGNMENT_TRANSFERRED,
            ProcurementEventType.TRANSFERRED_TO_ACCEPTANCE,
        }
    )
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request_id,
        request_number=record.request.request_number,
        event_id=event.id,
        action="Техническая приёмка завершена, оборудование оприходовано.",
        lines=record.current_revision.lines,
        recipient_user_ids=participants,
    )
    await db.flush()
    return await get_request_record(db, request_id)
