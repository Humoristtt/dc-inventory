from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.config import Settings
from app.modules.access.schemas import AccessRequestOut, AccessStateOut
from app.modules.access.service import (
    AccessAlreadyApprovedError,
    AccessBlockedError,
    create_or_get_access_request,
    get_pending_access_request,
)
from app.modules.auth.dependencies import Authenticated, DbSession
from app.modules.identity.models import AccessRequest
from app.modules.telegram_bot.service import (
    TelegramDeliveryConfigurationError,
    enqueue_access_request_admin_notification,
)

router = APIRouter(prefix="/api/access-requests", tags=["access"])


def _request_out(access_request: AccessRequest | None) -> AccessRequestOut | None:
    if access_request is None:
        return None
    return AccessRequestOut(
        id=access_request.id,
        status=access_request.status,
        requested_at=access_request.requested_at,
    )


@router.get("/me", response_model=AccessStateOut)
async def get_my_access_request(
    response: Response,
    db: DbSession,
    authenticated: Authenticated,
) -> AccessStateOut:
    access_request = await get_pending_access_request(db, authenticated.user.id)
    response.headers["Cache-Control"] = "no-store"
    return AccessStateOut(
        access_status=authenticated.user.access_status,
        request=_request_out(access_request),
    )


@router.post("", response_model=AccessStateOut)
async def request_access(
    request: Request,
    response: Response,
    db: DbSession,
    authenticated: Authenticated,
) -> AccessStateOut:
    try:
        result = await create_or_get_access_request(db, authenticated.user.id)
    except AccessAlreadyApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="access already approved",
        ) from exc
    except AccessBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access blocked",
        ) from exc

    settings: Settings = request.app.state.settings
    try:
        await enqueue_access_request_admin_notification(
            db,
            access_request=result.request,
            identity=authenticated.identity,
            settings=settings,
        )
    except TelegramDeliveryConfigurationError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="access notification unavailable",
        ) from exc

    await db.commit()
    await db.refresh(result.request)
    response.headers["Cache-Control"] = "no-store"
    return AccessStateOut(
        access_status=result.access_status,
        request=_request_out(result.request),
    )
