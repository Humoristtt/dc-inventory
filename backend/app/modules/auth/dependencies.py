from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.modules.auth.service import AuthenticatedContext, load_auth_context

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


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

    context = await load_auth_context(db, raw_token)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
        )

    return context


Authenticated = Annotated[AuthenticatedContext, Depends(get_authenticated_context)]
