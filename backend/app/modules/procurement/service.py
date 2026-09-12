from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from app.core.config import Settings
from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.models import Item
from app.modules.catalog.schemas import ItemCreate
from app.modules.catalog.service import get_item_record, validate_item_create_payload
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.identity.policy import Capability, has_capability
from app.modules.inventory.enums import MovementType
from app.modules.inventory.schemas import MovementCreate, MovementLineCreate
from app.modules.inventory.service import create_movement
from app.modules.procurement.enums import (
    ACTIVE_PROCUREMENT_STATUSES,
    ProcurementEventType,
    ProcurementLineType,
    ProcurementStatus,
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
    ExistingItemLineCreate,
    ExpectedStateMutation,
    LineBindingCreate,
    ManagerTransfer,
    ProcurementAcceptanceCreate,
    ProcurementLineCreate,
    ProcurementRequestCreate,
    ProposedItemLineCreate,
    RevisionCreate,
)
from app.modules.procurement.state_machine import transition_allowed


class ProcurementError(RuntimeError):
    code = "procurement_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ProcurementValidationError(ProcurementError):
    code = "procurement_validation_error"


class ProcurementNotFoundError(ProcurementError):
    code = "procurement_not_found"


class ProcurementConflictError(ProcurementError):
    code = "procurement_conflict"


class ProcurementForbiddenError(ProcurementError):
    code = "procurement_forbidden"


@dataclass(frozen=True, slots=True)
class ProcurementRecord:
    request: ProcurementRequest
    revisions: list[ProcurementRevision]
    events: list[ProcurementEvent]
    display_names: dict[uuid.UUID, str]

    @property
    def current_revision(self) -> ProcurementRevision:
        for revision in self.revisions:
            if revision.id == self.request.current_revision_id:
                return revision
        raise RuntimeError("procurement current revision was not loaded")


@dataclass(frozen=True, slots=True)
class ProcurementPage:
    items: list[ProcurementRecord]
    total: int


def _canonical_fingerprint(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_client_request_id(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ProcurementValidationError(
            "client_request_id must not be blank", code="client_request_id_required"
        )
    return normalized


def _normalize_comment(value: str | None, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ProcurementValidationError("comment is required", code="comment_required")
        return None
    normalized = value.strip()
    if not normalized:
        if required:
            raise ProcurementValidationError("comment is required", code="comment_required")
        return None
    return normalized


def _display_name(identity: TelegramIdentity | None, user_id: uuid.UUID) -> str:
    if identity is None:
        return str(user_id)
    name = " ".join(part for part in (identity.first_name, identity.last_name) if part).strip()
    if identity.username:
        return f"{name} (@{identity.username})" if name else f"@{identity.username}"
    return name or str(user_id)


async def _actor_snapshot(db: AsyncSession, user_id: uuid.UUID) -> str:
    identity = await db.scalar(select(TelegramIdentity).where(TelegramIdentity.user_id == user_id))
    return _display_name(identity, user_id)


async def _validate_manager(db: AsyncSession, user_id: uuid.UUID) -> User:
    manager = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if manager is None:
        raise ProcurementNotFoundError("manager not found", code="manager_not_found")
    if manager.role != UserRole.MANAGER or manager.access_status != UserAccessStatus.APPROVED:
        raise ProcurementValidationError(
            "assigned user must be an active Manager", code="manager_not_active"
        )
    return manager


async def list_managers(
    db: AsyncSession, *, limit: int, offset: int
) -> tuple[list[User], int, dict[uuid.UUID, str]]:
    filters = [User.role == UserRole.MANAGER, User.access_status == UserAccessStatus.APPROVED]
    total = int(await db.scalar(select(func.count(User.id)).where(*filters)) or 0)
    users = list(
        (
            await db.scalars(
                select(User)
                .where(*filters)
                .order_by(User.created_at, User.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    names = await _display_names(db, {user.id for user in users})
    return users, total, names


async def _display_names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, TelegramIdentity)
            .outerjoin(TelegramIdentity, TelegramIdentity.user_id == User.id)
            .where(User.id.in_(user_ids))
        )
    ).all()
    return {user_id: _display_name(identity, user_id) for user_id, identity in rows}


async def _prepare_lines(
    db: AsyncSession,
    payloads: Sequence[ProcurementLineCreate],
    revision_id: uuid.UUID,
) -> list[ProcurementRevisionLine]:
    rows: list[ProcurementRevisionLine] = []
    for line_no, payload in enumerate(payloads, 1):
        snapshot: dict[str, object]
        catalog_item_id: uuid.UUID | None
        if isinstance(payload, ExistingItemLineCreate):
            record = await get_item_record(db, payload.item_id)
            if record.item.status != ItemStatus.ACTIVE:
                raise ProcurementConflictError(
                    "archived item cannot be procured", code="catalog_item_archived"
                )
            snapshot = {
                "category_key": record.category.key,
                "category_name": record.category.display_name,
                "manufacturer_id": (
                    str(record.manufacturer.id) if record.manufacturer is not None else None
                ),
                "manufacturer_name": (
                    record.manufacturer.name if record.manufacturer is not None else None
                ),
                "name": record.item.name,
                "model": record.item.model,
                "attributes": {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in record.attributes.items()
                },
            }
            catalog_item_id = record.item.id
        elif isinstance(payload, ProposedItemLineCreate):
            validated = await validate_item_create_payload(
                db,
                ItemCreate(
                    category_key=payload.category_key,
                    manufacturer_id=payload.manufacturer_id,
                    name=payload.name,
                    model=payload.model,
                    attributes=payload.attributes,
                ),
            )
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
                quantity=payload.quantity,
            )
        )
    return rows


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
    raw = "|".join([namespace, *(str(part) for part in parts)])
    key = int.from_bytes(hashlib.sha256(raw.encode()).digest()[:8], "big", signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(key)))


def _payload_fingerprint(payload: object) -> str:
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    if not isinstance(data, dict):
        raise TypeError("mutation payload must serialize to an object")
    return _canonical_fingerprint(data)


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


def _record_options() -> tuple[ExecutableOption, ...]:
    return (
        selectinload(ProcurementRequest.revisions)
        .selectinload(ProcurementRevision.lines)
        .selectinload(ProcurementRevisionLine.binding),
        selectinload(ProcurementRequest.events),
    )


async def get_request_record(
    db: AsyncSession, request_id: uuid.UUID, *, lock: bool = False
) -> ProcurementRecord:
    statement = (
        select(ProcurementRequest)
        .where(ProcurementRequest.id == request_id)
        .options(*_record_options())
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    request = await db.scalar(statement)
    if request is None:
        raise ProcurementNotFoundError("procurement request not found")
    revisions = list(request.revisions)
    events = list(request.events)
    ids = {request.initiator_user_id, request.assigned_manager_user_id}
    ids.update(revision.submitted_by_user_id for revision in revisions)
    ids.update(event.actor_user_id for event in events)
    names = await _display_names(db, ids)
    return ProcurementRecord(request, revisions, events, names)


async def list_requests(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    view: str,
    limit: int,
    offset: int,
) -> ProcurementPage:
    filters = []
    if view == "my":
        filters.append(ProcurementRequest.assigned_manager_user_id == actor_user_id)
        filters.append(ProcurementRequest.status.in_(ACTIVE_PROCUREMENT_STATUSES))
    elif view == "active":
        filters.append(ProcurementRequest.status.in_(ACTIVE_PROCUREMENT_STATUSES))
    elif view == "history":
        filters.append(ProcurementRequest.status == ProcurementStatus.COMPLETED)
    else:
        raise ProcurementValidationError("unknown procurement view", code="view_invalid")
    total = int(await db.scalar(select(func.count(ProcurementRequest.id)).where(*filters)) or 0)
    requests = list(
        (
            await db.scalars(
                select(ProcurementRequest)
                .where(*filters)
                .options(*_record_options())
                .order_by(ProcurementRequest.created_at.desc(), ProcurementRequest.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .unique()
        .all()
    )
    user_ids: set[uuid.UUID] = set()
    for request in requests:
        user_ids.update((request.initiator_user_id, request.assigned_manager_user_id))
        user_ids.update(revision.submitted_by_user_id for revision in request.revisions)
        user_ids.update(event.actor_user_id for event in request.events)
    names = await _display_names(db, user_ids)
    return ProcurementPage(
        items=[
            ProcurementRecord(row, list(row.revisions), list(row.events), names) for row in requests
        ],
        total=total,
    )


async def _lock_and_validate_expected(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ExpectedStateMutation,
    *,
    actor_user_id: uuid.UUID,
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
        db, request_id, payload, actor_user_id=actor_user_id
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
        db, request_id, payload, actor_user_id=actor_user_id
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
        db, request_id, payload, actor_user_id=actor_user_id
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
        db, request_id, payload, actor_user_id=actor_user_id
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
        db, request_id, payload, actor_user_id=actor_user_id
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
        db, request_id, payload, actor_user_id=actor_user_id
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
        db, request_id, payload, actor_user_id=actor_user_id
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


def _bound_item_id(line: ProcurementRevisionLine) -> uuid.UUID | None:
    if line.catalog_item_id is not None:
        return line.catalog_item_id
    return line.binding.item_id if line.binding is not None else None


async def complete_acceptance(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ProcurementAcceptanceCreate,
    *,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> ProcurementRecord:
    record, key, fingerprint, replay = await _lock_and_validate_expected(
        db, request_id, payload, actor_user_id=actor_user_id
    )
    if replay is not None:
        return record
    _require_status(record.request, ProcurementStatus.AWAITING_ACCEPTANCE)
    quantities: defaultdict[uuid.UUID, int] = defaultdict(int)
    for line in record.current_revision.lines:
        item_id = _bound_item_id(line)
        if item_id is None:
            raise ProcurementConflictError(
                "all proposed lines must be bound", code="unbound_procurement_line"
            )
        quantities[item_id] += line.quantity
        if quantities[item_id] > 2**53 - 1:
            raise ProcurementValidationError("aggregated item quantity is too large")
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
