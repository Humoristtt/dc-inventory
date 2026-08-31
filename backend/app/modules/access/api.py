from fastapi import APIRouter, HTTPException, Response, status

from app.modules.access.schemas import AccessRequestOut, AccessStateOut
from app.modules.access.service import (
    AccessAlreadyApprovedError,
    AccessBlockedError,
    AccessRejectedError,
    create_or_get_access_request,
    get_pending_access_request,
)
from app.modules.auth.dependencies import Authenticated, DbSession
from app.modules.identity.models import AccessRequest

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
    except AccessRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="access request rejected; contact administrator",
        ) from exc
    except AccessBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access blocked",
        ) from exc

    await db.commit()
    await db.refresh(result.request)
    response.headers["Cache-Control"] = "no-store"
    return AccessStateOut(
        access_status=result.access_status,
        request=_request_out(result.request),
    )
