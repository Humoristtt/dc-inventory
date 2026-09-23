"""Explicit, confirmed account reset; historic inventory records are retained."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.dependencies import DbSession, ManageUsers
from app.modules.identity.admin_service import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    OutstandingCustodyInvariantError,
    RecoveryAdminInvariantError,
)
from app.modules.identity.reset_service import (
    AccountResetActiveProcurementError,
    AccountResetIdentityMismatchError,
    reset_user_account,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


class ResetUserAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A stale confirmation cannot silently reset a different Telegram account.
    telegram_user_id: int = Field(gt=0)
    confirmation: Literal["СБРОСИТЬ"]


@router.post("/{user_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_admin_user_account(
    user_id: UUID,
    payload: ResetUserAccountRequest,
    request: Request,
    db: DbSession,
    admin: ManageUsers,
) -> Response:
    try:
        await reset_user_account(
            db,
            actor_user_id=admin.user.id,
            target_user_id=user_id,
            expected_telegram_user_id=payload.telegram_user_id,
            recovery_telegram_user_id=request.app.state.settings.admin_telegram_user_id,
        )
        await db.commit()
    except AdminUserNotFoundError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "admin_user_not_found", "message": str(exc)},
        ) from exc
    except AdminUserForbiddenError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_user_forbidden", "message": str(exc)},
        ) from exc
    except (
        RecoveryAdminInvariantError,
        OutstandingCustodyInvariantError,
        AccountResetActiveProcurementError,
        AccountResetIdentityMismatchError,
    ) as exc:
        await db.rollback()
        if isinstance(exc, RecoveryAdminInvariantError):
            code = "admin_user_recovery_invariant"
        elif isinstance(exc, OutstandingCustodyInvariantError):
            code = "admin_user_outstanding_custody"
        elif isinstance(exc, AccountResetActiveProcurementError):
            code = "admin_user_active_procurement"
        else:
            code = "admin_user_reset_identity_mismatch"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": str(exc)},
        ) from exc

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )
