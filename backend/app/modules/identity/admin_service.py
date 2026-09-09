from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import String, func, or_, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement

from app.modules.auth.models import AuthSession
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import (
    TelegramIdentity,
    User,
    UserAccessEvent,
)

ADMIN_MANAGEMENT_LOCK_KEY = 4937638921054812071


class AdminUserError(RuntimeError):
    """Base administrative user-management error."""


class AdminUserNotFoundError(AdminUserError):
    """Target user does not exist."""


class InvalidAccessTransitionError(AdminUserError):
    """Requested access transition is not allowed."""


class RecoveryAdminInvariantError(AdminUserError):
    """Configured recovery administrator must remain usable."""


class LastApprovedAdminInvariantError(AdminUserError):
    """At least one approved administrator must remain usable."""


@dataclass(frozen=True, slots=True)
class AdminUserPage:
    items: list[User]
    total: int


@dataclass(frozen=True, slots=True)
class UserAccessEventPage:
    items: list[UserAccessEvent]
    total: int


async def get_admin_user(
    db: AsyncSession,
    user_id: UUID,
) -> User | None:
    return cast(
        User | None,
        await db.scalar(
            select(User)
            .where(User.id == user_id)
            .options(joinedload(User.telegram_identity))
        ),
    )


def _search_filters(
    *,
    query: str | None,
    role: UserRole | None,
    access_status: UserAccessStatus | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []

    if role is not None:
        filters.append(User.role == role)

    if access_status is not None:
        filters.append(User.access_status == access_status)

    if query:
        value = query.strip()
        if value:
            pattern = f"%{value}%"
            filters.append(
                or_(
                    TelegramIdentity.username.ilike(pattern),
                    TelegramIdentity.first_name.ilike(pattern),
                    TelegramIdentity.last_name.ilike(pattern),
                    sql_cast(
                        TelegramIdentity.telegram_user_id,
                        String,
                    ).ilike(pattern),
                )
            )

    return filters


async def list_admin_users(
    db: AsyncSession,
    *,
    query: str | None = None,
    role: UserRole | None = None,
    access_status: UserAccessStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AdminUserPage:
    filters = _search_filters(
        query=query,
        role=role,
        access_status=access_status,
    )

    total = await db.scalar(
        select(func.count(User.id))
        .select_from(User)
        .outerjoin(
            TelegramIdentity,
            TelegramIdentity.user_id == User.id,
        )
        .where(*filters)
    )

    rows = (
        await db.scalars(
            select(User)
            .outerjoin(
                TelegramIdentity,
                TelegramIdentity.user_id == User.id,
            )
            .where(*filters)
            .options(joinedload(User.telegram_identity))
            .order_by(User.created_at.desc(), User.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return AdminUserPage(
        items=list(rows),
        total=int(total or 0),
    )


async def list_user_access_events(
    db: AsyncSession,
    *,
    target_user_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> UserAccessEventPage:
    total = await db.scalar(
        select(func.count(UserAccessEvent.id)).where(
            UserAccessEvent.target_user_id == target_user_id
        )
    )

    rows = (
        await db.scalars(
            select(UserAccessEvent)
            .where(
                UserAccessEvent.target_user_id == target_user_id
            )
            .order_by(
                UserAccessEvent.occurred_at.desc(),
                UserAccessEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return UserAccessEventPage(
        items=list(rows),
        total=int(total or 0),
    )


async def update_user_access(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    target_user_id: UUID,
    access_status: UserAccessStatus,
    recovery_telegram_user_id: int | None,
    now: datetime | None = None,
) -> tuple[User, UserAccessEvent | None]:
    current_time = now or datetime.now(UTC)

    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                ADMIN_MANAGEMENT_LOCK_KEY
            )
        )
    )

    actor = cast(
        User | None,
        await db.scalar(
            select(User)
            .where(User.id == actor_user_id)
            .with_for_update()
        ),
    )
    if (
        actor is None
        or actor.role != UserRole.ADMIN
        or actor.access_status != UserAccessStatus.APPROVED
    ):
        raise InvalidAccessTransitionError(
            "actor is not an approved administrator"
        )

    target = cast(
        User | None,
        await db.scalar(
            select(User)
            .where(User.id == target_user_id)
            .with_for_update()
        ),
    )
    if target is None:
        raise AdminUserNotFoundError

    before_access = target.access_status

    if access_status == before_access:
        return target, None

    allowed = {
        (
            UserAccessStatus.APPROVED,
            UserAccessStatus.BLOCKED,
        ),
        (
            UserAccessStatus.BLOCKED,
            UserAccessStatus.APPROVED,
        ),
    }
    if (before_access, access_status) not in allowed:
        raise InvalidAccessTransitionError(
            "access lifecycle only supports APPROVED <-> BLOCKED; "
            "pending/rejected users use the access-request workflow"
        )

    identity = cast(
        TelegramIdentity | None,
        await db.scalar(
            select(TelegramIdentity).where(
                TelegramIdentity.user_id == target.id
            )
        ),
    )

    if (
        recovery_telegram_user_id is not None
        and identity is not None
        and identity.telegram_user_id
        == recovery_telegram_user_id
        and access_status != UserAccessStatus.APPROVED
    ):
        raise RecoveryAdminInvariantError(
            "configured recovery administrator "
            "must remain APPROVED"
        )

    if (
        target.role == UserRole.ADMIN
        and before_access == UserAccessStatus.APPROVED
        and access_status == UserAccessStatus.BLOCKED
    ):
        approved_admin_count = await db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.access_status == UserAccessStatus.APPROVED,
            )
        )

        if int(approved_admin_count or 0) <= 1:
            raise LastApprovedAdminInvariantError(
                "last approved administrator cannot be blocked"
            )

    target.access_status = access_status

    if access_status == UserAccessStatus.APPROVED:
        target.approved_at = current_time
        target.approved_by_user_id = actor_user_id

    else:
        target.approved_at = None
        target.approved_by_user_id = None

        await db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == target.id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=current_time)
        )

    event = UserAccessEvent(
        actor_user_id=actor_user_id,
        target_user_id=target.id,
        before_access_status=before_access,
        after_access_status=access_status,
        occurred_at=current_time,
    )
    db.add(event)

    await db.flush()
    return target, event
