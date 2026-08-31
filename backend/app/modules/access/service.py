from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus
from app.modules.identity.models import AccessRequest, User


class AccessRequestError(RuntimeError):
    """Базовая ошибка запроса доступа."""


class AccessAlreadyApprovedError(AccessRequestError):
    """Доступ уже предоставлен."""


class AccessBlockedError(AccessRequestError):
    """Пользователь заблокирован администратором."""


@dataclass(frozen=True, slots=True)
class AccessRequestResult:
    request: AccessRequest
    access_status: UserAccessStatus
    created: bool


async def get_pending_access_request(
    db: AsyncSession,
    user_id: UUID,
) -> AccessRequest | None:
    statement = (
        select(AccessRequest)
        .where(
            AccessRequest.user_id == user_id,
            AccessRequest.status == AccessRequestStatus.PENDING,
        )
        .order_by(AccessRequest.requested_at.desc())
        .limit(1)
    )
    result = await db.scalars(statement)
    return result.first()


async def create_or_get_access_request(
    db: AsyncSession,
    user_id: UUID,
) -> AccessRequestResult:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )
    if user is None:
        raise RuntimeError("authenticated user no longer exists")

    if user.access_status == UserAccessStatus.APPROVED:
        raise AccessAlreadyApprovedError
    if user.access_status == UserAccessStatus.BLOCKED:
        raise AccessBlockedError
    if user.access_status == UserAccessStatus.REJECTED:
        user.access_status = UserAccessStatus.PENDING
        user.approved_at = None
        user.approved_by_user_id = None

    existing = await get_pending_access_request(db, user.id)
    if existing is not None:
        return AccessRequestResult(
            request=existing,
            access_status=user.access_status,
            created=False,
        )

    access_request = AccessRequest(
        user_id=user.id,
        status=AccessRequestStatus.PENDING,
    )
    db.add(access_request)
    await db.flush()
    return AccessRequestResult(
        request=access_request,
        access_status=user.access_status,
        created=True,
    )
