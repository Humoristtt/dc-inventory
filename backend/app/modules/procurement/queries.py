from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.procurement.domain import (
    ProcurementNotFoundError,
    ProcurementPage,
    ProcurementRecord,
    ProcurementSummaryRecord,
    ProcurementValidationError,
    _display_name,
)
from app.modules.procurement.enums import (
    ACTIVE_PROCUREMENT_STATUSES,
    ProcurementStatus,
)
from app.modules.procurement.models import (
    ProcurementRequest,
    ProcurementRevision,
    ProcurementRevisionLine,
)


async def list_managers(
    db: AsyncSession,
    *,
    query: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[User], int, dict[uuid.UUID, str]]:
    filters = [
        User.role == UserRole.MANAGER,
        User.access_status == UserAccessStatus.APPROVED,
    ]

    user_query = select(User)
    count_query = select(func.count(User.id)).select_from(User)

    search = " ".join(query.split()) if query else ""

    if search:
        username_search = search.removeprefix("@") or search
        search_pattern = f"%{search}%"
        username_pattern = f"%{username_search}%"

        identity_filter = or_(
            TelegramIdentity.username.ilike(username_pattern),
            TelegramIdentity.first_name.ilike(search_pattern),
            TelegramIdentity.last_name.ilike(search_pattern),
            func.concat_ws(
                " ",
                TelegramIdentity.first_name,
                TelegramIdentity.last_name,
            ).ilike(search_pattern),
        )

        user_query = user_query.outerjoin(
            TelegramIdentity,
            TelegramIdentity.user_id == User.id,
        )
        count_query = count_query.outerjoin(
            TelegramIdentity,
            TelegramIdentity.user_id == User.id,
        )
        filters.append(identity_filter)

    total = int(await db.scalar(count_query.where(*filters)) or 0)

    users = list(
        (
            await db.scalars(
                user_query.where(*filters)
                .order_by(
                    User.created_at,
                    User.id,
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )

    names = await _display_names(
        db,
        {user.id for user in users},
    )

    return users, total, names


async def _display_names(
    db: AsyncSession,
    user_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}

    rows = (
        await db.execute(
            select(User.id, TelegramIdentity)
            .outerjoin(
                TelegramIdentity,
                TelegramIdentity.user_id == User.id,
            )
            .where(User.id.in_(user_ids))
        )
    ).all()

    return {
        user_id: _display_name(identity, user_id)
        for user_id, identity in rows
    }


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
    rows = (
        await db.execute(
            select(ProcurementRequest, ProcurementRevision)
            .join(
                ProcurementRevision,
                ProcurementRevision.id == ProcurementRequest.current_revision_id,
            )
            .where(*filters)
            .order_by(ProcurementRequest.created_at.desc(), ProcurementRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    user_ids = {
        user_id
        for request, _revision in rows
        for user_id in (request.initiator_user_id, request.assigned_manager_user_id)
    }
    names = await _display_names(db, user_ids)
    return ProcurementPage(
        items=[
            ProcurementSummaryRecord(
                request=request,
                current_revision=revision,
                display_names=names,
            )
            for request, revision in rows
        ],
        total=total,
    )
