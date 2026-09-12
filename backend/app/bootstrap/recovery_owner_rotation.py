"""Guarded maintenance-only recovery OWNER rotation."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.modules.auth.models import AuthSession
from app.modules.identity.access_lifecycle import transition_user_access
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.locking import (
    acquire_identity_management_exclusive_barrier,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    User,
    UserRoleEvent,
)
from app.modules.inventory.models import UserItemCustodyBalance

CONFIRMATION = "ROTATE_RECOVERY_OWNER"


class RecoveryOwnerRotationError(RuntimeError):
    pass


def assert_production_runtime(
    *,
    app_env: str,
    database_url: str,
) -> None:
    url = make_url(database_url)

    if app_env != "production":
        raise RecoveryOwnerRotationError(
            "recovery OWNER rotation requires APP_ENV=production"
        )

    if (
        url.drivername != "postgresql+asyncpg"
        or url.host != "postgres"
    ):
        raise RecoveryOwnerRotationError(
            "recovery OWNER rotation requires the production Docker "
            "PostgreSQL boundary"
        )


async def rotate_recovery_owner_transaction(
    db: AsyncSession,
    *,
    configured_recovery_telegram_user_id: int,
    target_telegram_user_id: int,
    confirmed_target_user_id: UUID,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = now or datetime.now(UTC)

    if (
        configured_recovery_telegram_user_id
        == target_telegram_user_id
    ):
        raise RecoveryOwnerRotationError(
            "current and target recovery identities must differ"
        )

    await acquire_identity_management_exclusive_barrier(
        db
    )

    current_identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.telegram_user_id
            == configured_recovery_telegram_user_id
        )
    )
    if current_identity is None:
        raise RecoveryOwnerRotationError(
            "configured recovery Telegram identity not found"
        )

    target_identity = await db.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.telegram_user_id
            == target_telegram_user_id
        )
    )
    if target_identity is None:
        raise RecoveryOwnerRotationError(
            "target Telegram identity not found; target must authenticate "
            "in the Mini App before rotation"
        )

    if target_identity.user_id != confirmed_target_user_id:
        raise RecoveryOwnerRotationError(
            "confirmed target user UUID does not match target Telegram identity"
        )

    if current_identity.user_id == target_identity.user_id:
        raise RecoveryOwnerRotationError(
            "current and target recovery identities resolve to the same user"
        )

    user_ids = sorted(
        (
            current_identity.user_id,
            target_identity.user_id,
        ),
        key=str,
    )

    locked_users = list(
        (
            await db.scalars(
                select(User)
                .where(User.id.in_(user_ids))
                .order_by(User.id)
                .with_for_update()
            )
        ).all()
    )
    users = {user.id: user for user in locked_users}

    current_owner = users.get(current_identity.user_id)
    target_user = users.get(target_identity.user_id)

    if current_owner is None or target_user is None:
        raise RecoveryOwnerRotationError(
            "recovery rotation user disappeared while acquiring locks"
        )

    owner_ids = list(
        (
            await db.scalars(
                select(User.id)
                .where(User.role == UserRole.OWNER)
                .with_for_update()
            )
        ).all()
    )

    if owner_ids != [current_owner.id]:
        raise RecoveryOwnerRotationError(
            "configured recovery identity is not the unique current OWNER"
        )

    if current_owner.access_status != UserAccessStatus.APPROVED:
        raise RecoveryOwnerRotationError(
            "current OWNER is not APPROVED"
        )

    if target_user.role == UserRole.OWNER:
        raise RecoveryOwnerRotationError(
            "target user is already OWNER"
        )

    if (
        await db.scalar(
            select(UserItemCustodyBalance.id)
            .where(
                UserItemCustodyBalance.user_id
                == target_user.id
            )
            .limit(1)
        )
        is not None
    ):
        raise RecoveryOwnerRotationError(
            "target has outstanding equipment custody"
        )

    target_before_role = target_user.role

    current_owner.role = UserRole.ADMIN
    db.add(
        UserRoleEvent(
            actor_user_id=current_owner.id,
            target_user_id=current_owner.id,
            before_role=UserRole.OWNER,
            after_role=UserRole.ADMIN,
            occurred_at=current_time,
        )
    )

    await db.flush()

    if target_user.access_status != UserAccessStatus.APPROVED:
        transition_user_access(
            db,
            user=target_user,
            actor_user_id=current_owner.id,
            access_status=UserAccessStatus.APPROVED,
            now=current_time,
        )
    else:
        if target_user.approved_at is None:
            target_user.approved_at = current_time
        if target_user.approved_by_user_id is None:
            target_user.approved_by_user_id = current_owner.id

    pending_request = await db.scalar(
        select(AccessRequest)
        .where(
            AccessRequest.user_id == target_user.id,
            AccessRequest.status
            == AccessRequestStatus.PENDING,
        )
        .with_for_update()
    )

    if pending_request is not None:
        pending_request.status = AccessRequestStatus.APPROVED
        pending_request.decided_at = current_time
        pending_request.decided_by_user_id = current_owner.id
        pending_request.decision_note = "recovery OWNER rotation"

    target_user.role = UserRole.OWNER
    db.add(
        UserRoleEvent(
            actor_user_id=current_owner.id,
            target_user_id=target_user.id,
            before_role=target_before_role,
            after_role=UserRole.OWNER,
            occurred_at=current_time,
        )
    )

    await db.flush()

    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id.in_(
                [current_owner.id, target_user.id]
            ),
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=current_time)
    )

    owner_count = int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.OWNER)
        )
        or 0
    )
    resulting_owner_id = await db.scalar(
        select(User.id).where(User.role == UserRole.OWNER)
    )

    if (
        owner_count != 1
        or resulting_owner_id != target_user.id
    ):
        raise RecoveryOwnerRotationError(
            "post-rotation singleton OWNER verification failed"
        )

    return {
        "old_owner_user_id": str(current_owner.id),
        "old_owner_role": UserRole.ADMIN.value,
        "new_owner_user_id": str(target_user.id),
        "new_owner_telegram_user_id": target_telegram_user_id,
        "new_owner_role": UserRole.OWNER.value,
        "new_owner_access_status": target_user.access_status.value,
        "active_sessions_revoked": True,
        "pending_access_request_resolved": (
            pending_request is not None
        ),
        "owner_count": owner_count,
    }


async def run_rotation(
    args: argparse.Namespace,
) -> dict[str, object]:
    settings = get_settings()

    assert_production_runtime(
        app_env=settings.app_env,
        database_url=settings.database_url,
    )

    if args.confirm != CONFIRMATION:
        raise RecoveryOwnerRotationError(
            f"explicit confirmation required: --confirm {CONFIRMATION}"
        )

    configured_id = settings.admin_telegram_user_id

    if configured_id is None:
        raise RecoveryOwnerRotationError(
            "ADMIN_TELEGRAM_USER_ID is not configured"
        )

    if configured_id != args.current_telegram_user_id:
        raise RecoveryOwnerRotationError(
            "current Telegram ID does not match configured "
            "ADMIN_TELEGRAM_USER_ID"
        )

    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    try:
        async with (
            AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db,
            db.begin(),
        ):
            result = await rotate_recovery_owner_transaction(
                db,
                configured_recovery_telegram_user_id=(
                    args.current_telegram_user_id
                ),
                target_telegram_user_id=(
                    args.target_telegram_user_id
                ),
                confirmed_target_user_id=(
                    args.target_user_id
                ),
            )
    finally:
        await engine.dispose()

    return {
        "state": "success",
        "next_recovery_telegram_user_id": (
            args.target_telegram_user_id
        ),
        **result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument(
        "--current-telegram-user-id",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--target-telegram-user-id",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--target-user-id",
        required=True,
        type=UUID,
    )
    parser.add_argument(
        "--confirm",
        required=True,
    )

    result = asyncio.run(
        run_rotation(parser.parse_args())
    )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
