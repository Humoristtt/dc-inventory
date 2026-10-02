from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.procurement.domain import (
    ProcurementNotFoundError,
    ProcurementValidationError,
    _display_name,
)


async def _actor_snapshot(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> str:
    identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.user_id
            == user_id
        )
    )
    return _display_name(
        identity,
        user_id,
    )


async def _validate_manager(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> User:
    manager = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )

    if manager is None:
        raise ProcurementNotFoundError(
            "manager not found",
            code="manager_not_found",
        )

    if (
        manager.role != UserRole.MANAGER
        or manager.access_status
        != UserAccessStatus.APPROVED
    ):
        raise ProcurementValidationError(
            "assigned user must be an active Manager",
            code="manager_not_active",
        )

    return manager
