from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import (
    advisory_lock_key,
    canonical_fingerprint,
)
from app.modules.identity.enums import UserAccessStatus
from app.modules.identity.models import User
from app.modules.identity.policy import Capability, has_capability
from app.modules.procurement.domain import (
    ProcurementConflictError,
    ProcurementForbiddenError,
    ProcurementRecord,
    _normalize_client_request_id,
)
from app.modules.procurement.enums import (
    ProcurementEventType,
    ProcurementStatus,
)
from app.modules.procurement.models import (
    ProcurementEvent,
    ProcurementRequest,
)
from app.modules.procurement.queries import get_request_record
from app.modules.procurement.schemas import ExpectedStateMutation
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


async def _lock_and_require_actor_capabilities(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    capabilities: tuple[Capability, ...],
) -> None:
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
