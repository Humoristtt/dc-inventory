from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db_session
from app.modules.auth.service import (
    AuthenticatedContext,
    RecoveryOwnerConflictError,
    load_auth_context,
    reconcile_recovery_owner,
)
from app.modules.identity.enums import UserAccessStatus
from app.modules.identity.policy import Capability, has_capability

DbSession = Annotated[AsyncSession, Depends(get_db_session)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _configured_web_app_origin(settings: Settings) -> str:
    parsed = urlsplit(settings.telegram_web_app_url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname

    if hostname is None:
        return f"{scheme}://{parsed.netloc.lower()}"

    host = hostname.lower()
    if ":" in host:
        host = f"[{host}]"

    port = parsed.port
    default_port = (
        443
        if scheme == "https"
        else 80
        if scheme == "http"
        else None
    )

    if port is not None and port != default_port:
        host = f"{host}:{port}"

    return f"{scheme}://{host}"

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

    try:
        recovery_changed = await reconcile_recovery_owner(
            db,
            user=context.user,
            identity=context.identity,
            settings=settings,
        )
        if recovery_changed:
            await db.commit()
    except RecoveryOwnerConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "configured recovery identity conflicts "
                "with existing owner"
            ),
        ) from exc

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


async def get_manage_users_context(
    approved: Approved,
) -> AuthenticatedContext:
    if not has_capability(
        approved.user.role,
        Capability.ACCESS_MANAGE_USERS,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="required capability missing",
        )
    return approved




def require_capability(
    capability: Capability,
) -> Callable[[Approved], Awaitable[AuthenticatedContext]]:
    async def dependency(approved: Approved) -> AuthenticatedContext:
        if not has_capability(approved.user.role, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="required capability missing",
            )
        return approved

    return dependency


def require_any_capability(
    *capabilities: Capability,
) -> Callable[[Approved], Awaitable[AuthenticatedContext]]:
    required = frozenset(capabilities)

    async def dependency(approved: Approved) -> AuthenticatedContext:
        if not any(
            has_capability(approved.user.role, capability)
            for capability in required
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="required capability missing",
            )
        return approved

    return dependency


CatalogRead = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.CATALOG_READ)),
]
CatalogManage = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.CATALOG_MANAGE)),
]
CatalogArchive = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.CATALOG_ARCHIVE)),
]
CatalogDeleteUnused = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.CATALOG_DELETE_UNUSED)),
]
InventoryRead = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.INVENTORY_READ)),
]
InventoryOperate = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.INVENTORY_OPERATE)),
]
InventoryAdmin = Annotated[
    AuthenticatedContext,
    Depends(require_capability(Capability.INVENTORY_ADMIN)),
]
MovementRead = Annotated[
    AuthenticatedContext,
    Depends(
        require_any_capability(
            Capability.MOVEMENT_READ_OWN,
            Capability.MOVEMENT_READ_ALL,
        )
    ),
]
ManageUsers = Annotated[
    AuthenticatedContext,
    Depends(get_manage_users_context),
]
