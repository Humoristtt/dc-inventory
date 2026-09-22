"""Administrative account reset, preserving immutable warehouse/audit foreign keys.

The old User is retained as a non-login audit tombstone: its Telegram identity is
removed, its sessions are revoked and future Telegram authentication creates a
new PENDING/ENGINEER User. This is deliberately not a physical users-row wipe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuthSession
from app.modules.identity.access_lifecycle import transition_user_access
from app.modules.identity.admin_service import (
    AdminUserForbiddenError,
    AdminUserNotFoundError,
    OutstandingCustodyInvariantError,
    RecoveryAdminInvariantError,
    _lock_actor_and_target,
)
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    UserRoleEvent,
)
from app.modules.identity.policy import Capability, has_capability
from app.modules.inventory.models import UserItemCustodyBalance
from app.modules.notifications.models import NotificationOutbox
from app.modules.notifications.service import notification_dedupe_key
from app.modules.procurement.enums import ProcurementStatus
from app.modules.procurement.models import ProcurementRequest


class AccountResetIdentityMismatchError(RuntimeError):
    """Confirmation Telegram ID no longer matches the selected account."""


class AccountResetActiveProcurementError(RuntimeError):
    """An unfinished procurement still depends on the selected user."""


async def reset_user_account(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    target_user_id: UUID,
    expected_telegram_user_id: int,
    recovery_telegram_user_id: int | None,
    now: datetime | None = None,
) -> None:
    """Detach a login atomically. Caller owns the transaction and commits once.

    Lock order starts with the Telegram-ID advisory lock used by auth upsert,
    then the shared identity-management barrier and the actor/target row locks.
    The identity is rechecked after the locks to reject stale UI confirmations.
    """
    current_time = now or datetime.now(UTC)

    initial_telegram_id = await db.scalar(
        select(TelegramIdentity.telegram_user_id).where(
            TelegramIdentity.user_id == target_user_id
        )
    )
    if initial_telegram_id is None:
        raise AdminUserNotFoundError("user has no active Telegram account")
    if initial_telegram_id != expected_telegram_user_id:
        raise AccountResetIdentityMismatchError("Telegram ID confirmation mismatch")

    # Auth upsert takes precisely this advisory lock before looking up an
    # identity. Without it a concurrent login could reuse the old account.
    await db.execute(select(func.pg_advisory_xact_lock(initial_telegram_id)))

    actor, target = await _lock_actor_and_target(
        db,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
    )

    if actor.id == target.id:
        raise AdminUserForbiddenError("self account reset is forbidden")

    identity = await db.scalar(
        select(TelegramIdentity)
        .where(TelegramIdentity.user_id == target.id)
        .with_for_update()
    )
    if identity is None:
        raise AdminUserNotFoundError("user has no active Telegram account")
    if identity.telegram_user_id != expected_telegram_user_id:
        raise AccountResetIdentityMismatchError("Telegram ID confirmation mismatch")

    if target.role == UserRole.OWNER or (
        recovery_telegram_user_id is not None
        and identity.telegram_user_id == recovery_telegram_user_id
    ):
        raise RecoveryAdminInvariantError("owner/recovery identity cannot be reset")

    if target.role == UserRole.ADMIN and not has_capability(
        actor.role, Capability.ACCESS_ASSIGN_ADMIN
    ):
        raise AdminUserForbiddenError("only owner may reset administrator accounts")

    if await db.scalar(
        select(UserItemCustodyBalance.id)
        .where(UserItemCustodyBalance.user_id == target.id)
        .limit(1)
    ) is not None:
        raise OutstandingCustodyInvariantError(
            "return outstanding equipment before resetting this account"
        )

    if await db.scalar(
        select(ProcurementRequest.id)
        .where(
            ProcurementRequest.status != ProcurementStatus.COMPLETED,
            or_(
                ProcurementRequest.initiator_user_id == target.id,
                ProcurementRequest.assigned_manager_user_id == target.id,
            ),
        )
        .limit(1)
    ) is not None:
        raise AccountResetActiveProcurementError(
            "finish or reassign active procurement before account reset"
        )

    # An old session can never authenticate again: revoke it and remove the
    # identity that load_auth_context additionally requires.
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == target.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=current_time)
    )

    # Invalidate unprocessed approval buttons: callbacks cascade from deleted
    # pending requests. Existing decided requests and access/role events remain.
    pending_requests = (
        await db.scalars(
            select(AccessRequest)
            .where(
                AccessRequest.user_id == target.id,
                AccessRequest.status == AccessRequestStatus.PENDING,
            )
            .with_for_update()
        )
    ).all()
    for request in pending_requests:
        await db.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.dedupe_key == notification_dedupe_key(
                    "access-request", request.id, "admin"
                ),
                NotificationOutbox.status == "PENDING",
                NotificationOutbox.claimed_at.is_(None),
            )
            .values(status="DEAD", last_error="account reset")
        )
    await db.execute(
        delete(AccessRequest).where(
            AccessRequest.user_id == target.id,
            AccessRequest.status == AccessRequestStatus.PENDING,
        )
    )

    transition_user_access(
        db,
        user=target,
        actor_user_id=actor.id,
        access_status=UserAccessStatus.BLOCKED,
        now=current_time,
    )
    if target.role != UserRole.ENGINEER:
        db.add(
            UserRoleEvent(
                actor_user_id=actor.id,
                target_user_id=target.id,
                before_role=target.role,
                after_role=UserRole.ENGINEER,
                occurred_at=current_time,
            )
        )
        target.role = UserRole.ENGINEER

    # Referential integrity requires retaining the historical User row.
    # Deleting the identity removes the unique Telegram ID association so the
    # next validated initData creates an entirely new PENDING account.
    await db.delete(identity)
    await db.flush()
