from uuid import UUID

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.modules.auth.dependencies import Admin, DbSession
from app.modules.identity.admin_schemas import (
    AdminUserOut,
    AdminUserPageOut,
    AdminUserPatch,
    UserAccessEventOut,
    UserAccessEventPageOut,
)
from app.modules.identity.admin_service import (
    AdminUserNotFoundError,
    InvalidAccessTransitionError,
    LastApprovedAdminInvariantError,
    OutstandingCustodyInvariantError,
    RecoveryAdminInvariantError,
    get_admin_user,
    list_admin_users,
    list_user_access_events,
    update_user_access,
)
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import User, UserAccessEvent

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
)


def _user_out(user: User) -> AdminUserOut:
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
    )


def _event_out(
    event: UserAccessEvent,
) -> UserAccessEventOut:
    return UserAccessEventOut(
        id=event.id,
        actor_user_id=event.actor_user_id,
        target_user_id=event.target_user_id,
        before_access_status=event.before_access_status,
        after_access_status=event.after_access_status,
        occurred_at=event.occurred_at,
    )


@router.get("", response_model=AdminUserPageOut)
async def get_users(
    response: Response,
    db: DbSession,
    admin: Admin,
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
        items=[_user_out(user) for user in page.items],
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
    admin: Admin,
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

    response.headers["Cache-Control"] = "no-store"

    return UserAccessEventPageOut(
        items=[_event_out(event) for event in page.items],
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
    admin: Admin,
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

    except (
        InvalidAccessTransitionError,
        LastApprovedAdminInvariantError,
        OutstandingCustodyInvariantError,
        RecoveryAdminInvariantError,
    ) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    user = await get_admin_user(db, user_id)
    if user is None:
        raise RuntimeError(
            "managed user disappeared after committed update"
        )

    response.headers["Cache-Control"] = "no-store"
    return _user_out(user)
