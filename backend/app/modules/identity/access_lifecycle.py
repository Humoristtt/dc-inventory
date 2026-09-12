from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.enums import UserAccessStatus
from app.modules.identity.models import User, UserAccessEvent


def transition_user_access(
    db: AsyncSession,
    *,
    user: User,
    actor_user_id: UUID,
    access_status: UserAccessStatus,
    now: datetime | None = None,
) -> UserAccessEvent | None:
    before_access = user.access_status

    if before_access == access_status:
        return None

    current_time = now or datetime.now(UTC)

    user.access_status = access_status

    if access_status == UserAccessStatus.APPROVED:
        user.approved_at = current_time
        user.approved_by_user_id = actor_user_id
    else:
        user.approved_at = None
        user.approved_by_user_id = None

    event = UserAccessEvent(
        actor_user_id=actor_user_id,
        target_user_id=user.id,
        before_access_status=before_access,
        after_access_status=access_status,
        occurred_at=current_time,
    )
    db.add(event)
    return event
