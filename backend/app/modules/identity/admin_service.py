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
    UserRoleEvent,
)
from app.modules.identity.policy import (
    CUSTODY_ROLES,
    IDENTITY_MANAGEMENT_LOCK_KEY,
    STANDARD_ASSIGNABLE_ROLES,
    Capability,
    has_capability,
)
from app.modules.inventory.models import UserItemCustodyBalance


class AdminUserError(RuntimeError):
    """Base administrative user-management error."""


class AdminUserNotFoundError(AdminUserError):
    """Target user does not exist."""


class InvalidAccessTransitionError(AdminUserError):
    """Requested access transition is not allowed."""


class AdminUserForbiddenError(AdminUserError):
    """Actor may not perform the requested privileged mutation."""


class RecoveryAdminInvariantError(AdminUserError):
    """Configured recovery OWNER must remain usable."""


class InvalidRoleTransitionError(AdminUserError):
    """Requested role transition is not allowed."""


class OutstandingCustodyInvariantError(AdminUserError):
    """A blocked user must not retain warehouse custody."""


@dataclass(frozen=True, slots=True)
class AdminUserPage:
    items: list[User]
    total: int


@dataclass(frozen=True, slots=True)
class UserAccessEventPage:
    items: list[UserAccessEvent]
    total: int


@dataclass(frozen=True, slots=True)
class UserRoleEventPage:
    items: list[UserRoleEvent]
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


async def list_user_role_events(
    db: AsyncSession,
    *,
    target_user_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> UserRoleEventPage:
    total = await db.scalar(
        select(func.count(UserRoleEvent.id)).where(
            UserRoleEvent.target_user_id == target_user_id
        )
    )
    rows = (
        await db.scalars(
            select(UserRoleEvent)
            .where(UserRoleEvent.target_user_id == target_user_id)
            .order_by(
                UserRoleEvent.occurred_at.desc(),
                UserRoleEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return UserRoleEventPage(items=list(rows), total=int(total or 0))


async def _lock_actor_and_target(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    target_user_id: UUID,
) -> tuple[User, User]:
    await db.execute(
        select(func.pg_advisory_xact_lock(IDENTITY_MANAGEMENT_LOCK_KEY))
    )
    actor = cast(
        User | None,
        await db.scalar(
            select(User).where(User.id == actor_user_id).with_for_update()
        ),
    )
    if (
        actor is None
        or actor.access_status != UserAccessStatus.APPROVED
        or not has_capability(actor.role, Capability.ACCESS_MANAGE_USERS)
    ):
        raise AdminUserForbiddenError(
            "approved user-management capability required"
        )

    target = cast(
        User | None,
        await db.scalar(
            select(User).where(User.id == target_user_id).with_for_update()
        ),
    )
    if target is None:
        raise AdminUserNotFoundError
    return actor, target


async def _is_recovery_identity(
    db: AsyncSession,
    *,
    user_id: UUID,
    recovery_telegram_user_id: int | None,
) -> bool:
    if recovery_telegram_user_id is None:
        return False
    return (
        await db.scalar(
            select(TelegramIdentity.telegram_user_id).where(
                TelegramIdentity.user_id == user_id
            )
        )
        == recovery_telegram_user_id
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

    actor, target = await _lock_actor_and_target(
        db,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )

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

    if (
        target.role == UserRole.OWNER
        or await _is_recovery_identity(
            db,
            user_id=target.id,
            recovery_telegram_user_id=recovery_telegram_user_id,
        )
    ):
        raise RecoveryAdminInvariantError(
            "owner/recovery identity cannot be changed"
        )

    if (
        target.role == UserRole.ADMIN
        and not has_capability(actor.role, Capability.ACCESS_ASSIGN_ADMIN)
    ):
        raise AdminUserForbiddenError(
            "only owner may manage administrator access"
        )

    if actor.id == target.id:
        raise AdminUserForbiddenError("self access mutation is forbidden")

    if (
        before_access == UserAccessStatus.APPROVED
        and access_status == UserAccessStatus.BLOCKED
        and await db.scalar(
            select(UserItemCustodyBalance.id)
            .where(
                UserItemCustodyBalance.user_id == target.id
            )
            .limit(1)
        )
        is not None
    ):
        raise OutstandingCustodyInvariantError(
            "user with outstanding equipment custody cannot be blocked"
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


async def update_user_role(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    target_user_id: UUID,
    role: UserRole,
    recovery_telegram_user_id: int | None,
    now: datetime | None = None,
) -> tuple[User, UserRoleEvent | None]:
    current_time = now or datetime.now(UTC)
    actor, target = await _lock_actor_and_target(
        db,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )

    if actor.id == target.id:
        raise AdminUserForbiddenError("self role mutation is forbidden")
    if role == UserRole.OWNER:
        raise AdminUserForbiddenError("owner role cannot be assigned")
    if (
        target.role == UserRole.OWNER
        or await _is_recovery_identity(
            db,
            user_id=target.id,
            recovery_telegram_user_id=recovery_telegram_user_id,
        )
    ):
        raise RecoveryAdminInvariantError(
            "owner/recovery identity role cannot be changed"
        )
    if target.role == UserRole.ADMIN and not has_capability(
        actor.role,
        Capability.ACCESS_ASSIGN_ADMIN,
    ):
        raise AdminUserForbiddenError(
            "only owner may change administrator membership"
        )

    can_assign = (
        role in STANDARD_ASSIGNABLE_ROLES
        and has_capability(
            actor.role,
            Capability.ACCESS_ASSIGN_STANDARD_ROLES,
        )
    ) or (
        role == UserRole.ADMIN
        and has_capability(actor.role, Capability.ACCESS_ASSIGN_ADMIN)
    )
    if not can_assign:
        raise AdminUserForbiddenError("requested role cannot be assigned")

    before_role = target.role
    if role == before_role:
        return target, None

    if role not in CUSTODY_ROLES and await db.scalar(
        select(UserItemCustodyBalance.id)
        .where(UserItemCustodyBalance.user_id == target.id)
        .limit(1)
    ) is not None:
        raise OutstandingCustodyInvariantError(
            "outstanding equipment custody must be returned before role change"
        )

    target.role = role
    event = UserRoleEvent(
        actor_user_id=actor.id,
        target_user_id=target.id,
        before_role=before_role,
        after_role=role,
        occurred_at=current_time,
    )
    db.add(event)
    await db.flush()
    return target, event
