from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.safety import require_real_inventory_mutations_enabled
from app.db.errors import RETRYABLE_POSTGRES_SQLSTATES, postgres_sqlstate
from app.modules.auth.dependencies import (
    DbSession,
    ProcurementAccept,
    ProcurementCreate,
    ProcurementManage,
    ProcurementRead,
)
from app.modules.catalog.service import CatalogError
from app.modules.inventory.service import InventoryError
from app.modules.procurement.email import enqueue_procurement_email
from app.modules.procurement.enums import STATUS_LABELS
from app.modules.procurement.models import ProcurementEvent, ProcurementRevisionLine
from app.modules.procurement.schemas import (
    AssignmentMutation,
    CorrectionRequest,
    DiscrepancyCreate,
    ExpectedStateMutation,
    LineBindingCreate,
    ManagerTransfer,
    ProcurementAcceptanceCreate,
    ProcurementEmailCreate,
    ProcurementEmailOut,
    ProcurementEventOut,
    ProcurementLineOut,
    ProcurementManagerPageOut,
    ProcurementRequestCreate,
    ProcurementRequestOut,
    ProcurementRequestPageOut,
    ProcurementRequestSummaryOut,
    ProcurementRevisionOut,
    RevisionCreate,
    UserSummaryOut,
)
from app.modules.procurement.service import (
    ProcurementConflictError,
    ProcurementError,
    ProcurementForbiddenError,
    ProcurementNotFoundError,
    ProcurementRecord,
    available_actions,
    bind_line,
    complete_acceptance,
    create_request,
    get_request_record,
    list_managers,
    list_requests,
    manager_accept,
    report_discrepancy,
    return_for_correction,
    submit_revision,
    take_ownership,
    transfer_manager,
    transfer_to_acceptance,
)

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


def _raise_procurement_error(error: Exception) -> NoReturn:
    if isinstance(error, ProcurementNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ProcurementForbiddenError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(
        error,
        (ProcurementConflictError, CatalogError, InventoryError),
    ):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail_code = getattr(error, "code", "procurement_error")
    raise HTTPException(
        status_code=code,
        detail={"code": detail_code, "message": str(error)},
    ) from error


def _raise_db_error(error: DBAPIError) -> NoReturn:
    code = (
        "procurement_concurrency_conflict"
        if postgres_sqlstate(error) in RETRYABLE_POSTGRES_SQLSTATES
        else "procurement_database_conflict"
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": "procurement operation conflicts with current state"},
    ) from error


def _name(record: ProcurementRecord, user_id: UUID) -> UserSummaryOut:
    return UserSummaryOut(id=user_id, display_name=record.display_names.get(user_id, str(user_id)))


def _line_out(line: ProcurementRevisionLine) -> ProcurementLineOut:
    return ProcurementLineOut(
        id=line.id,
        line_no=line.line_no,
        line_type=line.line_type,
        catalog_item_id=line.catalog_item_id,
        bound_item_id=(line.catalog_item_id or (line.binding.item_id if line.binding else None)),
        display_snapshot=line.display_snapshot,
        quantity=line.quantity,
    )


def _revision_out(record: ProcurementRecord, revision: object) -> ProcurementRevisionOut:
    from app.modules.procurement.models import ProcurementRevision

    if not isinstance(revision, ProcurementRevision):
        raise TypeError("invalid revision")
    return ProcurementRevisionOut(
        id=revision.id,
        revision_number=revision.revision_number,
        submitted_by=_name(record, revision.submitted_by_user_id),
        general_comment=revision.general_comment,
        created_at=revision.created_at,
        lines=[_line_out(line) for line in revision.lines],
    )


def _event_out(record: ProcurementRecord, event: ProcurementEvent) -> ProcurementEventOut:
    return ProcurementEventOut(
        id=event.id,
        event_type=event.event_type,
        actor=UserSummaryOut(
            id=event.actor_user_id,
            display_name=event.actor_display_name_snapshot,
        ),
        from_status=event.from_status,
        to_status=event.to_status,
        revision_id=event.revision_id,
        comment=event.comment,
        metadata=event.metadata_json,
        occurred_at=event.occurred_at,
    )


def _summary(record: ProcurementRecord) -> ProcurementRequestSummaryOut:
    request = record.request
    revision = record.current_revision
    return ProcurementRequestSummaryOut(
        id=request.id,
        request_number=request.request_number,
        status=request.status,
        status_label=STATUS_LABELS[request.status],
        initiator=_name(record, request.initiator_user_id),
        assigned_manager=_name(record, request.assigned_manager_user_id),
        current_revision_id=request.current_revision_id,
        revision_number=revision.revision_number,
        line_count=revision.line_count,
        state_version=request.state_version,
        created_at=request.created_at,
        updated_at=request.updated_at,
        completed_at=request.completed_at,
    )


def _detail(record: ProcurementRecord, actor: object) -> ProcurementRequestOut:
    from app.modules.identity.models import User

    if not isinstance(actor, User):
        raise TypeError("invalid actor")
    summary = _summary(record)
    return ProcurementRequestOut(
        **summary.model_dump(),
        current_revision=_revision_out(record, record.current_revision),
        revisions=[_revision_out(record, revision) for revision in record.revisions],
        events=[_event_out(record, event) for event in record.events],
        final_movement_id=record.request.final_movement_id,
        available_actions=available_actions(record, actor),
    )


async def _mutate(
    call: Awaitable[ProcurementRecord],
    db: DbSession,
) -> ProcurementRecord:
    try:
        result = await call
        await db.commit()
        return result
    except (ProcurementError, CatalogError, InventoryError) as error:
        await db.rollback()
        _raise_procurement_error(error)
    except (IntegrityError, DBAPIError) as error:
        await db.rollback()
        _raise_db_error(error)


@router.get("/managers", response_model=ProcurementManagerPageOut)
async def get_managers(
    response: Response,
    db: DbSession,
    _approved: ProcurementRead,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProcurementManagerPageOut:
    users, total, names = await list_managers(db, limit=limit, offset=offset)
    response.headers["Cache-Control"] = "no-store"
    return ProcurementManagerPageOut(
        items=[UserSummaryOut(id=user.id, display_name=names[user.id]) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/requests", response_model=ProcurementRequestPageOut)
async def get_requests(
    response: Response,
    db: DbSession,
    approved: ProcurementRead,
    view: Literal["my", "active", "history"] = "active",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProcurementRequestPageOut:
    page = await list_requests(
        db, actor_user_id=approved.user.id, view=view, limit=limit, offset=offset
    )
    response.headers["Cache-Control"] = "no-store"
    return ProcurementRequestPageOut(
        items=[_summary(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/requests/{request_id}", response_model=ProcurementRequestOut)
async def get_request(
    request_id: UUID,
    response: Response,
    db: DbSession,
    approved: ProcurementRead,
) -> ProcurementRequestOut:
    try:
        record = await get_request_record(db, request_id)
    except ProcurementError as error:
        _raise_procurement_error(error)
    response.headers["Cache-Control"] = "no-store"
    return _detail(record, approved.user)


@router.post("/requests", response_model=ProcurementRequestOut, status_code=201)
async def post_request(
    payload: ProcurementRequestCreate,
    request: Request,
    response: Response,
    db: DbSession,
    approved: ProcurementCreate,
) -> ProcurementRequestOut:
    record = await _mutate(
        create_request(
            db,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    response.headers["Cache-Control"] = "no-store"
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/revisions", response_model=ProcurementRequestOut)
async def post_revision(
    request_id: UUID,
    payload: RevisionCreate,
    request: Request,
    db: DbSession,
    approved: ProcurementCreate,
) -> ProcurementRequestOut:
    record = await _mutate(
        submit_revision(
            db,
            request_id,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/manager-accept", response_model=ProcurementRequestOut)
async def post_manager_accept(
    request_id: UUID,
    payload: ExpectedStateMutation,
    db: DbSession,
    approved: ProcurementManage,
) -> ProcurementRequestOut:
    record = await _mutate(
        manager_accept(db, request_id, payload, actor_user_id=approved.user.id), db
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/return-for-correction", response_model=ProcurementRequestOut)
async def post_return_for_correction(
    request_id: UUID,
    payload: CorrectionRequest,
    request: Request,
    db: DbSession,
    approved: ProcurementManage,
) -> ProcurementRequestOut:
    record = await _mutate(
        return_for_correction(
            db,
            request_id,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/take-ownership", response_model=ProcurementRequestOut)
async def post_take_ownership(
    request_id: UUID,
    payload: AssignmentMutation,
    request: Request,
    db: DbSession,
    approved: ProcurementManage,
) -> ProcurementRequestOut:
    record = await _mutate(
        take_ownership(
            db,
            request_id,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/transfer-manager", response_model=ProcurementRequestOut)
async def post_transfer_manager(
    request_id: UUID,
    payload: ManagerTransfer,
    request: Request,
    db: DbSession,
    approved: ProcurementManage,
) -> ProcurementRequestOut:
    record = await _mutate(
        transfer_manager(
            db,
            request_id,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/transfer-to-acceptance", response_model=ProcurementRequestOut)
async def post_transfer_to_acceptance(
    request_id: UUID,
    payload: ExpectedStateMutation,
    request: Request,
    db: DbSession,
    approved: ProcurementManage,
) -> ProcurementRequestOut:
    record = await _mutate(
        transfer_to_acceptance(
            db,
            request_id,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/bind-line", response_model=ProcurementRequestOut)
async def post_bind_line(
    request_id: UUID,
    payload: LineBindingCreate,
    db: DbSession,
    approved: ProcurementAccept,
) -> ProcurementRequestOut:
    record = await _mutate(bind_line(db, request_id, payload, actor_user_id=approved.user.id), db)
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/discrepancies", response_model=ProcurementRequestOut)
async def post_discrepancy(
    request_id: UUID,
    payload: DiscrepancyCreate,
    request: Request,
    db: DbSession,
    approved: ProcurementAccept,
) -> ProcurementRequestOut:
    record = await _mutate(
        report_discrepancy(
            db,
            request_id,
            payload,
            comment=payload.comment,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/acceptance", response_model=ProcurementRequestOut)
async def post_acceptance(
    request_id: UUID,
    payload: ProcurementAcceptanceCreate,
    request: Request,
    db: DbSession,
    approved: ProcurementAccept,
) -> ProcurementRequestOut:
    require_real_inventory_mutations_enabled(request)
    record = await _mutate(
        complete_acceptance(
            db,
            request_id,
            payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        ),
        db,
    )
    return _detail(record, approved.user)


@router.post("/requests/{request_id}/email", response_model=ProcurementEmailOut, status_code=202)
async def post_email(
    request_id: UUID,
    payload: ProcurementEmailCreate,
    request: Request,
    db: DbSession,
    approved: ProcurementCreate,
) -> ProcurementEmailOut:
    try:
        record = await get_request_record(db, request_id, lock=True)
        row = await enqueue_procurement_email(
            db,
            record=record,
            payload=payload,
            actor_user_id=approved.user.id,
            settings=request.app.state.settings,
        )
        await db.commit()
    except ProcurementError as error:
        await db.rollback()
        _raise_procurement_error(error)
    except (IntegrityError, DBAPIError) as error:
        await db.rollback()
        _raise_db_error(error)
    return ProcurementEmailOut(id=row.id, status=row.status, dedupe_key=row.dedupe_key)
