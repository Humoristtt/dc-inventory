from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.modules.auth.service import AuthenticatedContext, load_auth_context
from app.modules.identity.enums import UserAccessStatus, UserRole

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _configured_web_app_origin(settings: Settings) -> str:
    parsed = urlsplit(settings.telegram_web_app_url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _enforce_cookie_mutation_origin(
    request: Request,
    settings: Settings,
) -> None:
    if request.method.upper() in SAFE_METHODS:
        return

    origin = request.headers.get("origin")
    expected_origin = _configured_web_app_origin(settings)

    if origin is None or origin.rstrip("/").lower() != expected_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cross-origin authenticated mutation forbidden",
        )


async def get_authenticated_context(
    request: Request,
    db: DbSession,
) -> AuthenticatedContext:
    settings: Settings = request.app.state.settings
    raw_token = request.cookies.get(settings.auth_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    _enforce_cookie_mutation_origin(request, settings)

    context = await load_auth_context(db, raw_token)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
        )

    return context


Authenticated = Annotated[AuthenticatedContext, Depends(get_authenticated_context)]

async def get_approved_context(
    authenticated: Authenticated,
) -> AuthenticatedContext:
    if authenticated.user.access_status != UserAccessStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access approval required",
        )
    return authenticated


Approved = Annotated[AuthenticatedContext, Depends(get_approved_context)]


async def get_admin_context(
    approved: Approved,
) -> AuthenticatedContext:
    if approved.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="administrator role required",
        )
    return approved


Admin = Annotated[AuthenticatedContext, Depends(get_admin_context)]
