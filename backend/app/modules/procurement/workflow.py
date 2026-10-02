from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.identity.policy import Capability
from app.modules.procurement.actors import (
    _actor_snapshot,
    _validate_manager,
)
from app.modules.procurement.domain import (
    ProcurementConflictError,
    ProcurementForbiddenError,
    ProcurementRecord,
    _normalize_client_request_id,
    _normalize_comment,
)
from app.modules.procurement.enums import (
    ACTIVE_PROCUREMENT_STATUSES,
    ProcurementEventType,
    ProcurementStatus,
)
from app.modules.procurement.lines import _prepare_lines
from app.modules.procurement.models import (
    ProcurementRequest,
    ProcurementRevision,
    ProcurementRevisionLine,
)
from app.modules.procurement.mutation_support import (
    _add_event,
    _advisory_lock,
    _lock_and_require_actor_capabilities,
    _lock_and_validate_expected,
    _next_request_number,
    _payload_fingerprint,
    _require_status,
    _set_status,
)
from app.modules.procurement.notifications import (
    enqueue_procurement_notifications,
    technical_recipient_user_ids,
)
from app.modules.procurement.queries import get_request_record
from app.modules.procurement.schemas import (
    AssignmentMutation,
    CorrectionRequest,
    ExpectedStateMutation,
    ManagerTransfer,
    ProcurementRequestCreate,
    RevisionCreate,
)


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
