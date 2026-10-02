from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.idempotency import (
    advisory_lock_key,
    canonical_fingerprint,
)
from app.modules.catalog.models import Item
from app.modules.catalog.service import (
    create_item,
    validate_item_create_payload,
)
from app.modules.identity.models import User
from app.modules.identity.policy import Capability, has_capability
from app.modules.inventory.enums import MovementType
from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
from app.modules.inventory.service import create_movement
from app.modules.procurement.actors import (
    _actor_snapshot,
    _validate_manager,
)
from app.modules.procurement.domain import (
    ProcurementConflictError,
    ProcurementError,
    ProcurementForbiddenError,
    ProcurementNotFoundError,
    ProcurementPage,
    ProcurementRecord,
    ProcurementServiceUnavailableError,
    ProcurementSummaryRecord,
    ProcurementValidationError,
    _normalize_client_request_id,
    _normalize_comment,
)
from app.modules.procurement.queries import (
    get_request_record,
    list_managers,
    list_requests,
)
from app.modules.procurement.enums import (
    ACTIVE_PROCUREMENT_STATUSES,
    ProcurementEventType,
    ProcurementLineType,
    ProcurementStatus,
)
from app.modules.procurement.lines import (
    _bound_item_id,
    _prepare_lines,
    _validate_aggregated_item_quantities,
)
from app.modules.procurement.models import (
    ProcurementEvent,
    ProcurementLineCatalogBinding,
    ProcurementRequest,
    ProcurementRevision,
    ProcurementRevisionLine,
)
from app.modules.procurement.notifications import (
    enqueue_procurement_notifications,
    technical_recipient_user_ids,
)
from app.modules.procurement.schemas import (
    AssignmentMutation,
    CorrectionRequest,
    ExpectedStateMutation,
    LineBindingCreate,
    ManagerTransfer,
    ProcurementAcceptanceCreate,
    ProcurementRequestCreate,
    ProposedItemCreateAndBind,
    RevisionCreate,
)
from app.modules.procurement.state_machine import transition_allowed


async def _next_request_number(db: AsyncSession) -> str:
    row = (
        await db.execute(
            select(
                func.to_char(func.current_date(), "YYYY"),
                func.nextval("procurement_request_number_seq"),
            )
        )
    ).one()
    return f"PR-{row[0]}-{int(row[1]):06d}"


async def _advisory_lock(db: AsyncSession, namespace: str, *parts: object) -> None:
    key = advisory_lock_key(namespace, *parts)
    await db.execute(select(func.pg_advisory_xact_lock(key)))


def _payload_fingerprint(payload: object) -> str:
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    if not isinstance(data, dict):
        raise TypeError("mutation payload must serialize to an object")
    return canonical_fingerprint(data)


async def _add_event(
    db: AsyncSession,
    *,
    request: ProcurementRequest,
    event_type: ProcurementEventType,
    actor_user_id: uuid.UUID,
    actor_snapshot: str,
    client_request_id: str,
    request_fingerprint: str,
    from_status: ProcurementStatus | None = None,
    to_status: ProcurementStatus | None = None,
    revision_id: uuid.UUID | None = None,
    comment: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ProcurementEvent:
    event = ProcurementEvent(
        id=uuid.uuid4(),
        request_id=request.id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        actor_display_name_snapshot=actor_snapshot,
        client_request_id=client_request_id,
        request_fingerprint=request_fingerprint,
        from_status=from_status,
        to_status=to_status,
        revision_id=revision_id,
        comment=comment,
        metadata_json=metadata,
    )
    db.add(event)
    await db.flush()
    return event


async def create_request(
    db: AsyncSession,
    payload: ProcurementRequestCreate,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_CREATE,),
    )

    request_key = _normalize_client_request_id(payload.client_request_id)
    fingerprint = _payload_fingerprint(payload)
    await _advisory_lock(db, "procurement-create", actor_user_id, request_key)
    existing = await db.scalar(
        select(ProcurementRequest).where(
            ProcurementRequest.initiator_user_id == actor_user_id,
            ProcurementRequest.creation_client_request_id == request_key,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise ProcurementConflictError(
                "idempotency key was used with another payload",
                code="idempotency_payload_conflict",
            )
        return await get_request_record(db, existing.id)

    await _validate_manager(db, payload.assigned_manager_user_id)
    request_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    lines = await _prepare_lines(db, payload.lines, revision_id)
    actor_snapshot = await _actor_snapshot(db, actor_user_id)
    request = ProcurementRequest(
        id=request_id,
        request_number=await _next_request_number(db),
        status=ProcurementStatus.AGREEMENT_PENDING_MANAGER,
        initiator_user_id=actor_user_id,
        assigned_manager_user_id=payload.assigned_manager_user_id,
        current_revision_id=revision_id,
        creation_client_request_id=request_key,
        request_fingerprint=fingerprint,
        state_version=1,
    )
    revision = ProcurementRevision(
        id=revision_id,
        request_id=request_id,
        revision_number=1,
        submitted_by_user_id=actor_user_id,
        submitted_by_display_name_snapshot=actor_snapshot,
        general_comment=_normalize_comment(payload.general_comment),
        line_count=len(lines),
    )
    db.add_all([request, revision, *lines])
    await db.flush()
    event = await _add_event(
        db,
        request=request,
        event_type=ProcurementEventType.REQUEST_CREATED,
        actor_user_id=actor_user_id,
        actor_snapshot=actor_snapshot,
        client_request_id=request_key,
        request_fingerprint=fingerprint,
        to_status=request.status,
        revision_id=revision.id,
    )
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request.id,
        request_number=request.request_number,
        event_id=event.id,
        action="Новая заявка. Ожидает обработки менеджером.",
        lines=lines,
        recipient_user_ids={request.assigned_manager_user_id},
    )
    return await get_request_record(db, request.id)


async def _lock_and_require_actor_capabilities(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    capabilities: tuple[Capability, ...],
) -> None:
    from app.modules.identity.enums import (
        UserAccessStatus,
    )
    from app.modules.identity.models import User

    actor = await db.scalar(
        select(User)
        .where(User.id == actor_user_id)
        .with_for_update()
        .execution_options(
            populate_existing=True,
        )
    )

    if (
        actor is None
        or actor.access_status != UserAccessStatus.APPROVED
        or any(
            not has_capability(
                actor.role,
                capability,
            )
            for capability in capabilities
        )
    ):
        raise ProcurementForbiddenError("required procurement capability is no longer available")


async def _lock_and_validate_expected(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ExpectedStateMutation,
    *,
    actor_user_id: uuid.UUID,
    event_type: ProcurementEventType,
) -> tuple[ProcurementRecord, str, str, ProcurementEvent | None]:
    record = await get_request_record(db, request_id, lock=True)
    client_request_id = _normalize_client_request_id(payload.client_request_id)
    fingerprint = _payload_fingerprint(payload)
    previous = await db.scalar(
        select(ProcurementEvent).where(
            ProcurementEvent.request_id == request_id,
            ProcurementEvent.actor_user_id == actor_user_id,
            ProcurementEvent.client_request_id == client_request_id,
        )
    )
    if previous is not None:
        if previous.event_type != event_type:
            raise ProcurementConflictError(
                "idempotency key was used for another procurement action",
                code="idempotency_action_conflict",
            )
        if previous.request_fingerprint != fingerprint:
            raise ProcurementConflictError(
                "idempotency key was used with another payload",
                code="idempotency_payload_conflict",
            )
        return record, client_request_id, fingerprint, previous
    if (
        record.request.state_version != payload.expected_state_version
        or record.request.current_revision_id != payload.expected_revision_id
    ):
        raise ProcurementConflictError(
            "procurement state is stale; refresh and retry", code="stale_state"
        )
    return record, client_request_id, fingerprint, None


def _require_status(
    request: ProcurementRequest,
    *expected: ProcurementStatus,
) -> None:
    if request.status not in expected:
        raise ProcurementConflictError(
            f"request status is {request.status}",
            code="invalid_transition",
        )


def _set_status(request: ProcurementRequest, target: ProcurementStatus) -> ProcurementStatus:
    previous = request.status
    if not transition_allowed(previous, target):
        raise ProcurementConflictError("invalid procurement transition", code="invalid_transition")
    request.status = target
    request.state_version += 1
    request.updated_at = datetime.now(UTC)
    return previous


async def manager_accept(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ExpectedStateMutation,
    *,
    actor_user_id: uuid.UUID,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.MANAGER_ACCEPTED,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_MANAGE,),
    )

    if replay is not None:
        return record
    previous = _set_status(record.request, ProcurementStatus.PURCHASING)
    await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.MANAGER_ACCEPTED,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        from_status=previous,
        to_status=record.request.status,
        revision_id=record.request.current_revision_id,
    )
    await db.flush()
    return await get_request_record(db, request_id)


def _proposal_metadata(lines: Sequence[ProcurementRevisionLine]) -> dict[str, object]:
    return {
        "alternative_proposal": [
            {
                "line_type": line.line_type.value,
                "quantity": line.quantity,
                "catalog_item_id": str(line.catalog_item_id) if line.catalog_item_id else None,
                "display_snapshot": line.display_snapshot,
            }
            for line in lines
        ]
    }


async def return_for_correction(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: CorrectionRequest,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.CORRECTION_REQUESTED,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_MANAGE,),
    )

    if replay is not None:
        return record
    _require_status(
        record.request,
        ProcurementStatus.AGREEMENT_PENDING_MANAGER,
        ProcurementStatus.AWAITING_ACCEPTANCE,
    )
    proposal: list[ProcurementRevisionLine] = []
    if payload.alternative_proposal:
        proposal = await _prepare_lines(db, payload.alternative_proposal, uuid.uuid4())
        # Proposal rows are serialized into the immutable event, never persisted
        # as an official revision or attached to the request.
    previous = _set_status(record.request, ProcurementStatus.AGREEMENT_REVISION_REQUIRED)
    event = await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.CORRECTION_REQUESTED,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        from_status=previous,
        to_status=record.request.status,
        revision_id=record.request.current_revision_id,
        comment=_normalize_comment(payload.comment, required=True),
        metadata=_proposal_metadata(proposal) if proposal else None,
    )
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request_id,
        request_number=record.request.request_number,
        event_id=event.id,
        action="Менеджер вернул заявку на корректировку.",
        lines=record.current_revision.lines,
        recipient_user_ids={record.request.initiator_user_id},
    )
    await db.flush()
    return await get_request_record(db, request_id)


async def submit_revision(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: RevisionCreate,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.REVISION_SUBMITTED,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_CREATE,),
    )

    if replay is not None:
        return record
    if record.request.initiator_user_id != actor_user_id:
        raise ProcurementForbiddenError("only the initiator may submit a revision")
    _require_status(record.request, ProcurementStatus.AGREEMENT_REVISION_REQUIRED)
    revision_id = uuid.uuid4()
    lines = await _prepare_lines(db, payload.lines, revision_id)
    revision_number = max(revision.revision_number for revision in record.revisions) + 1
    revision = ProcurementRevision(
        id=revision_id,
        request_id=request_id,
        revision_number=revision_number,
        submitted_by_user_id=actor_user_id,
        submitted_by_display_name_snapshot=await _actor_snapshot(db, actor_user_id),
        general_comment=_normalize_comment(payload.general_comment),
        line_count=len(lines),
    )
    db.add_all([revision, *lines])
    await db.flush()
    previous = _set_status(record.request, ProcurementStatus.AGREEMENT_PENDING_MANAGER)
    record.request.current_revision_id = revision_id
    event = await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.REVISION_SUBMITTED,
        actor_user_id=actor_user_id,
        actor_snapshot=revision.submitted_by_display_name_snapshot,
        client_request_id=key,
        request_fingerprint=fingerprint,
        from_status=previous,
        to_status=record.request.status,
        revision_id=revision_id,
    )
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request_id,
        request_number=record.request.request_number,
        event_id=event.id,
        action=f"Отправлена новая редакция №{revision_number}.",
        lines=lines,
        recipient_user_ids={record.request.assigned_manager_user_id},
    )
    await db.flush()
    return await get_request_record(db, request_id)


async def _change_assignment(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: AssignmentMutation,
    *,
    actor_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
    event_type: ProcurementEventType,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=event_type,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_MANAGE,),
    )

    if replay is not None:
        return record
    if record.request.status not in ACTIVE_PROCUREMENT_STATUSES:
        raise ProcurementConflictError("completed request cannot be reassigned")
    if record.request.assigned_manager_user_id != payload.expected_assigned_manager_user_id:
        raise ProcurementConflictError("manager assignment is stale", code="stale_assignment")
    await _validate_manager(db, target_user_id)
    previous_manager = record.request.assigned_manager_user_id
    if previous_manager == target_user_id:
        raise ProcurementConflictError("manager is already assigned", code="assignment_unchanged")
    record.request.assigned_manager_user_id = target_user_id
    record.request.state_version += 1
    record.request.updated_at = datetime.now(UTC)
    event = await _add_event(
        db,
        request=record.request,
        event_type=event_type,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        revision_id=record.request.current_revision_id,
        metadata={
            "from_manager_user_id": str(previous_manager),
            "to_manager_user_id": str(target_user_id),
        },
    )
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request_id,
        request_number=record.request.request_number,
        event_id=event.id,
        action="Вы назначены ответственным менеджером.",
        lines=record.current_revision.lines,
        recipient_user_ids={target_user_id},
    )
    await db.flush()
    return await get_request_record(db, request_id)


async def take_ownership(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: AssignmentMutation,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    return await _change_assignment(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        target_user_id=actor_user_id,
        event_type=ProcurementEventType.ASSIGNMENT_TAKEN,
        settings=settings,
    )


async def transfer_manager(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ManagerTransfer,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    return await _change_assignment(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        target_user_id=payload.manager_user_id,
        event_type=ProcurementEventType.ASSIGNMENT_TRANSFERRED,
        settings=settings,
    )


async def transfer_to_acceptance(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ExpectedStateMutation,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db,
        request_id,
        payload,
        actor_user_id=actor_user_id,
        event_type=ProcurementEventType.TRANSFERRED_TO_ACCEPTANCE,
    )
    await _lock_and_require_actor_capabilities(
        db,
        actor_user_id=actor_user_id,
        capabilities=(Capability.PROCUREMENT_MANAGE,),
    )

    if replay is not None:
        return record
    previous = _set_status(record.request, ProcurementStatus.AWAITING_ACCEPTANCE)
    event = await _add_event(
        db,
        request=record.request,
        event_type=ProcurementEventType.TRANSFERRED_TO_ACCEPTANCE,
        actor_user_id=actor_user_id,
        actor_snapshot=await _actor_snapshot(db, actor_user_id),
        client_request_id=key,
        request_fingerprint=fingerprint,
        from_status=previous,
        to_status=record.request.status,
        revision_id=record.request.current_revision_id,
    )
    recipients = await technical_recipient_user_ids(db)
    await enqueue_procurement_notifications(
        db,
        settings=settings,
        request_id=request_id,
        request_number=record.request.request_number,
        event_id=event.id,
        action="Поставка передана на техническую приёмку.",
        lines=record.current_revision.lines,
        recipient_user_ids=recipients,
    )
    await db.flush()
    return await get_request_record(db, request_id)


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


def available_actions(record: ProcurementRecord, actor: User) -> list[str]:
    request = record.request
    actions: list[str] = []
    if (
        has_capability(actor.role, Capability.PROCUREMENT_MANAGE)
        and request.status in ACTIVE_PROCUREMENT_STATUSES
    ):
        if request.assigned_manager_user_id != actor.id:
            actions.append("take_ownership")
        actions.append("transfer_manager")
        if request.status == ProcurementStatus.AGREEMENT_PENDING_MANAGER:
            actions.extend(("manager_accept", "return_for_correction"))
        elif request.status == ProcurementStatus.PURCHASING:
            actions.append("transfer_to_acceptance")
        elif request.status == ProcurementStatus.AWAITING_ACCEPTANCE:
            actions.append("return_for_correction")
    if (
        has_capability(actor.role, Capability.PROCUREMENT_CREATE)
        and actor.id == request.initiator_user_id
        and request.status == ProcurementStatus.AGREEMENT_REVISION_REQUIRED
    ):
        actions.append("submit_revision")
    if has_capability(actor.role, Capability.PROCUREMENT_ACCEPT):
        if request.status != ProcurementStatus.COMPLETED and any(
            line.line_type == ProcurementLineType.PROPOSED_ITEM and line.binding is None
            for line in record.current_revision.lines
        ):
            actions.append("bind_lines")
        if request.status == ProcurementStatus.AWAITING_ACCEPTANCE:
            actions.extend(("report_discrepancy", "complete_acceptance"))
    return actions
