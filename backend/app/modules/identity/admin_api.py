from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.modules.auth.dependencies import DbSession, ManageUsers
from app.modules.identity.admin_schemas import (
    AdminUserAccessRequestDecision,
    AdminUserOut,
    AdminUserPageOut,
    AdminUserPatch,
    AdminUserRolePatch,
    UserAccessEventOut,
    UserAccessEventPageOut,
    UserRoleEventOut,
    UserRoleEventPageOut,
)
from app.modules.identity.admin_service import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    InvalidAccessTransitionError,
    InvalidRoleTransitionError,
    OutstandingCustodyInvariantError,
    PendingAccessRequestNotFoundError,
    RecoveryAdminInvariantError,
    decide_pending_access_request,
    get_admin_user,
    get_user_display_names,
    list_admin_users,
    list_user_access_events,
    list_user_role_events,
    update_user_access,
    update_user_role,
)
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import User, UserAccessEvent, UserRoleEvent
from app.modules.telegram_bot.service import (
    enqueue_access_decision_user_notification,
)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
)


def _admin_error_detail(
    error: Exception,
) -> dict[str, str]:
    if isinstance(
        error,
        OutstandingCustodyInvariantError,
    ):
        code = "admin_user_outstanding_custody"
    elif isinstance(
        error,
        RecoveryAdminInvariantError,
    ):
        code = "admin_user_recovery_invariant"
    elif isinstance(
        error,
        InvalidAccessTransitionError,
    ):
        code = "admin_user_invalid_access_transition"
    elif isinstance(
        error,
        InvalidRoleTransitionError,
    ):
        code = "admin_user_invalid_role_transition"
    elif isinstance(
        error,
        PendingAccessRequestNotFoundError,
    ):
        code = "admin_user_pending_access_request_not_found"
    elif isinstance(
        error,
        AdminUserForbiddenError,
    ):
        code = "admin_user_forbidden"
    elif isinstance(
        error,
        AdminUserNotFoundError,
    ):
        code = "admin_user_not_found"
    else:
        code = "admin_user_error"

    message = str(error).strip() or code

    return {
        "code": code,
        "message": message,
    }


def _user_out(
    user: User,
    recovery_telegram_user_id: int | None,
) -> AdminUserOut:
    identity = user.telegram_identity
    if identity is None:
        raise RuntimeError("managed user has no Telegram identity")

    return AdminUserOut(
        id=user.id,
        telegram_user_id=identity.telegram_user_id,
        username=identity.username,
        first_name=identity.first_name,
        last_name=identity.last_name,
        role=user.role,
        access_status=user.access_status,
        created_at=user.created_at,
        updated_at=user.updated_at,
        approved_at=user.approved_at,
        is_recovery_identity=(
            recovery_telegram_user_id is not None
            and identity.telegram_user_id == recovery_telegram_user_id
        ),
    )


def _event_out(
    event: UserAccessEvent,
    actor_display_name: str,
) -> UserAccessEventOut:
    return UserAccessEventOut(
        id=event.id,
        actor_user_id=event.actor_user_id,
        actor_display_name=actor_display_name,
        target_user_id=event.target_user_id,
        before_access_status=event.before_access_status,
        after_access_status=event.after_access_status,
        occurred_at=event.occurred_at,
    )


def _role_event_out(
    event: UserRoleEvent,
    actor_display_name: str,
) -> UserRoleEventOut:
    return UserRoleEventOut(
        id=event.id,
        actor_user_id=event.actor_user_id,
        actor_display_name=actor_display_name,
        target_user_id=event.target_user_id,
        before_role=event.before_role,
        after_role=event.after_role,
        occurred_at=event.occurred_at,
    )


@router.get("", response_model=AdminUserPageOut)
async def get_users(
    request: Request,
    response: Response,
    db: DbSession,
    admin: ManageUsers,
    q: str | None = Query(default=None, max_length=100),
    role: UserRole | None = None,
    access_status: UserAccessStatus | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminUserPageOut:
    del admin

    page = await list_admin_users(
        db,
        query=q,
        role=role,
        access_status=access_status,
        limit=limit,
        offset=offset,
    )

    response.headers["Cache-Control"] = "no-store"

    return AdminUserPageOut(
        items=[
            _user_out(
                user,
                request.app.state.settings.admin_telegram_user_id,
            )
            for user in page.items
        ],
        total=page.total,
    )


@router.get(
    "/{user_id}/events",
    response_model=UserAccessEventPageOut,
)
async def get_user_events(
    user_id: UUID,
    response: Response,
    db: DbSession,
    admin: ManageUsers,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UserAccessEventPageOut:
    del admin

    user = await get_admin_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    page = await list_user_access_events(
        db,
        target_user_id=user_id,
        limit=limit,
        offset=offset,
    )

    actor_names = await get_user_display_names(
        db,
        {
            event.actor_user_id
            for event in page.items
        },
    )

    response.headers["Cache-Control"] = "no-store"

    return UserAccessEventPageOut(
        items=[
            _event_out(
                event,
                actor_names.get(
                    event.actor_user_id,
                    str(event.actor_user_id),
                ),
            )
            for event in page.items
        ],
        total=page.total,
    )


@router.get(
    "/{user_id}/role-events",
    response_model=UserRoleEventPageOut,
)
async def get_user_role_events(
    user_id: UUID,
    response: Response,
    db: DbSession,
    admin: ManageUsers,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UserRoleEventPageOut:
    del admin
    user = await get_admin_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    page = await list_user_role_events(
        db,
        target_user_id=user_id,
        limit=limit,
        offset=offset,
    )
    actor_names = await get_user_display_names(
        db,
        {
            event.actor_user_id
            for event in page.items
        },
    )

    response.headers["Cache-Control"] = "no-store"
    return UserRoleEventPageOut(
        items=[
            _role_event_out(
                event,
                actor_names.get(
                    event.actor_user_id,
                    str(event.actor_user_id),
                ),
            )
            for event in page.items
        ],
        total=page.total,
    )


@router.patch(
    "/{user_id}",
    response_model=AdminUserOut,
)
async def patch_user(
    user_id: UUID,
    payload: AdminUserPatch,
    request: Request,
    response: Response,
    db: DbSession,
    admin: ManageUsers,
) -> AdminUserOut:
    try:
        await update_user_access(
            db,
            actor_user_id=admin.user.id,
            target_user_id=user_id,
            access_status=payload.access_status,
            recovery_telegram_user_id=(
                request.app.state.settings.admin_telegram_user_id
            ),
        )
        await db.commit()

    except AdminUserNotFoundError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        ) from exc

    except AdminUserForbiddenError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_admin_error_detail(exc),
        ) from exc

    except (
        InvalidAccessTransitionError,
        OutstandingCustodyInvariantError,
        RecoveryAdminInvariantError,
    ) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_admin_error_detail(exc),
        ) from exc

    user = await get_admin_user(db, user_id)
    if user is None:
        raise RuntimeError(
            "managed user disappeared after committed update"
        )

    response.headers["Cache-Control"] = "no-store"
    return _user_out(
        user,
        request.app.state.settings.admin_telegram_user_id,
    )


@router.post(
    "/{user_id}/access-request-decision",
    response_model=AdminUserOut,
)
async def post_access_request_decision(
    user_id: UUID,
    payload: AdminUserAccessRequestDecision,
    request: Request,
    response: Response,
    db: DbSession,
    admin: ManageUsers,
) -> AdminUserOut:
    decision = (
        AccessRequestStatus.APPROVED
        if payload.decision == "APPROVE"
        else AccessRequestStatus.REJECTED
    )

    try:
        _, access_request, _ = await decide_pending_access_request(
            db,
            actor_user_id=admin.user.id,
            target_user_id=user_id,
            decision=decision,
            recovery_telegram_user_id=(
                request.app.state.settings.admin_telegram_user_id
            ),
        )

        managed_user = await get_admin_user(db, user_id)
        if managed_user is None:
            raise RuntimeError(
                "managed user disappeared during access decision"
            )

        identity = managed_user.telegram_identity
        if identity is None:
            raise RuntimeError(
                "managed user has no Telegram identity"
            )

        await enqueue_access_decision_user_notification(
            db,
            access_request_id=access_request.id,
            target_identity=identity,
            status=access_request.status,
            settings=request.app.state.settings,
        )

        await db.commit()

    except AdminUserNotFoundError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        ) from exc

    except AdminUserForbiddenError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_admin_error_detail(exc),
        ) from exc

    except (
        InvalidAccessTransitionError,
        PendingAccessRequestNotFoundError,
        RecoveryAdminInvariantError,
    ) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_admin_error_detail(exc),
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return _user_out(
        managed_user,
        request.app.state.settings.admin_telegram_user_id,
    )


@router.patch(
    "/{user_id}/role",
    response_model=AdminUserOut,
)
async def patch_user_role(
    user_id: UUID,
    payload: AdminUserRolePatch,
    request: Request,
    response: Response,
    db: DbSession,
    admin: ManageUsers,
) -> AdminUserOut:
    try:
        await update_user_role(
            db,
            actor_user_id=admin.user.id,
            target_user_id=user_id,
            role=payload.role,
            recovery_telegram_user_id=(
                request.app.state.settings.admin_telegram_user_id
            ),
        )
        await db.commit()
    except AdminUserNotFoundError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        ) from exc
    except AdminUserForbiddenError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_admin_error_detail(exc),
        ) from exc
    except (
        InvalidRoleTransitionError,
        OutstandingCustodyInvariantError,
        RecoveryAdminInvariantError,
    ) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_admin_error_detail(exc),
        ) from exc

    user = await get_admin_user(db, user_id)
    if user is None:
        raise RuntimeError("managed user disappeared after committed update")
    response.headers["Cache-Control"] = "no-store"
    return _user_out(
        user,
        request.app.state.settings.admin_telegram_user_id,
    )
