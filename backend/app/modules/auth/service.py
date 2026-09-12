from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.modules.auth.models import AuthSession
from app.modules.auth.telegram import ValidatedTelegramInitData
from app.modules.identity.access_lifecycle import transition_user_access
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    User,
    UserRoleEvent,
)
from app.modules.identity.policy import IDENTITY_MANAGEMENT_LOCK_KEY

SESSION_TOKEN_BYTES = 32
MAX_ACTIVE_SESSIONS_PER_USER = 5


@dataclass(frozen=True, slots=True)
class IssuedAuthSession:
    session: AuthSession
    raw_token: str


@dataclass(frozen=True, slots=True)
class AuthenticatedContext:
    session: AuthSession
    user: User
    identity: TelegramIdentity


class RecoveryOwnerConflictError(RuntimeError):
    """Configured recovery identity conflicts with an existing OWNER."""


def hash_session_token(raw_token: str) -> bytes:
    return hashlib.sha256(raw_token.encode("utf-8")).digest()


async def reconcile_recovery_owner(
    db: AsyncSession,
    *,
    user: User,
    identity: TelegramIdentity,
    settings: Settings,
    now: datetime | None = None,
) -> bool:
    recovery_telegram_user_id = settings.admin_telegram_user_id

    if (
        recovery_telegram_user_id is None
        or identity.telegram_user_id != recovery_telegram_user_id
    ):
        return False

    if (
        user.role == UserRole.OWNER
        and user.access_status == UserAccessStatus.APPROVED
        and user.approved_at is not None
        and user.approved_by_user_id is not None
        and await db.scalar(
            select(AccessRequest.id)
            .where(
                AccessRequest.user_id == user.id,
                AccessRequest.status == AccessRequestStatus.PENDING,
            )
            .limit(1)
        )
        is None
    ):
        return False

    current_time = now or datetime.now(UTC)

    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                IDENTITY_MANAGEMENT_LOCK_KEY
            )
        )
    )

    locked_user = await db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
    )
    if locked_user is None:
        raise RuntimeError(
            "configured recovery user no longer exists"
        )

    conflicting_owner_id = await db.scalar(
        select(User.id)
        .where(
            User.role == UserRole.OWNER,
            User.id != locked_user.id,
        )
        .limit(1)
    )
    if conflicting_owner_id is not None:
        raise RecoveryOwnerConflictError(
            "configured recovery identity conflicts with existing owner"
        )

    changed = False

    if locked_user.role != UserRole.OWNER:
        before_role = locked_user.role
        locked_user.role = UserRole.OWNER
        db.add(
            UserRoleEvent(
                actor_user_id=locked_user.id,
                target_user_id=locked_user.id,
                before_role=before_role,
                after_role=UserRole.OWNER,
                occurred_at=current_time,
            )
        )
        changed = True

    access_event = transition_user_access(
        db,
        user=locked_user,
        actor_user_id=locked_user.id,
        access_status=UserAccessStatus.APPROVED,
        now=current_time,
    )
    if access_event is not None:
        changed = True
    elif (
        locked_user.approved_at is None
        or locked_user.approved_by_user_id is None
    ):
        locked_user.approved_at = current_time
        locked_user.approved_by_user_id = locked_user.id
        changed = True

    pending_request = (
        await db.scalars(
            select(AccessRequest)
            .where(
                AccessRequest.user_id == locked_user.id,
                AccessRequest.status == AccessRequestStatus.PENDING,
            )
            .with_for_update()
        )
    ).first()

    if pending_request is not None:
        pending_request.status = AccessRequestStatus.APPROVED
        pending_request.decided_at = current_time
        pending_request.decided_by_user_id = locked_user.id
        pending_request.decision_note = "configured recovery owner"
        changed = True

    if changed:
        await db.flush()

    return changed


async def upsert_telegram_identity(
    db: AsyncSession,
    validated: ValidatedTelegramInitData,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> tuple[User, TelegramIdentity]:
    current_time = now or datetime.now(UTC)
    telegram_user_id = validated.user.id

    # Сериализуем первый вход одного Telegram ID. Это закрывает race создания
    # двух User/TelegramIdentity при параллельных auth-запросах.
    await db.execute(select(func.pg_advisory_xact_lock(telegram_user_id)))

    identity = await db.scalar(
        select(TelegramIdentity)
        .where(TelegramIdentity.telegram_user_id == telegram_user_id)
        .options(joinedload(TelegramIdentity.user))
    )

    is_recovery_identity = settings.admin_telegram_user_id == telegram_user_id

    if identity is None:
        if is_recovery_identity:
            await db.execute(
                select(
                    func.pg_advisory_xact_lock(
                        IDENTITY_MANAGEMENT_LOCK_KEY
                    )
                )
            )

        if is_recovery_identity and await db.scalar(
            select(User.id).where(User.role == UserRole.OWNER).limit(1)
        ) is not None:
            raise RecoveryOwnerConflictError(
                "configured recovery identity conflicts with existing owner"
            )
        user = User(
            role=UserRole.OWNER if is_recovery_identity else UserRole.ENGINEER,
            access_status=(
                UserAccessStatus.APPROVED
                if is_recovery_identity
                else UserAccessStatus.PENDING
            ),
            approved_at=current_time if is_recovery_identity else None,
        )
        identity = TelegramIdentity(
            user=user,
            telegram_user_id=telegram_user_id,
            username=validated.user.username,
            first_name=validated.user.first_name,
            last_name=validated.user.last_name,
            language_code=validated.user.language_code,
            last_auth_at=current_time,
        )
        db.add(user)
        db.add(identity)
        await db.flush()
        return user, identity

    user = identity.user
    identity.username = validated.user.username
    identity.first_name = validated.user.first_name
    identity.last_name = validated.user.last_name
    identity.language_code = validated.user.language_code
    identity.last_auth_at = current_time

    if is_recovery_identity:
        await reconcile_recovery_owner(
            db,
            user=user,
            identity=identity,
            settings=settings,
            now=current_time,
        )

    await db.flush()
    return user, identity


async def issue_auth_session(
    db: AsyncSession,
    user: User,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> IssuedAuthSession:
    current_time = now or datetime.now(UTC)

    locked_user_id = await db.scalar(
        select(User.id)
        .where(User.id == user.id)
        .with_for_update()
    )

    if locked_user_id is None:
        raise RuntimeError(
            "cannot issue session for missing user"
        )

    active_filter = (
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > current_time,
    )

    active_count = await db.scalar(
        select(func.count(AuthSession.id)).where(
            *active_filter
        )
    )

    revoke_count = max(
        0,
        int(active_count or 0)
        - MAX_ACTIVE_SESSIONS_PER_USER
        + 1,
    )

    if revoke_count:
        oldest_sessions = (
            await db.scalars(
                select(AuthSession)
                .where(*active_filter)
                .order_by(
                    AuthSession.created_at.asc(),
                    AuthSession.id.asc(),
                )
                .limit(revoke_count)
                .with_for_update()
            )
        ).all()

        for existing_session in oldest_sessions:
            existing_session.revoked_at = current_time

    raw_token = secrets.token_urlsafe(
        SESSION_TOKEN_BYTES
    )

    session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        created_at=current_time,
        expires_at=(
            current_time
            + timedelta(seconds=ttl_seconds)
        ),
    )

    db.add(session)
    await db.flush()

    return IssuedAuthSession(
        session=session,
        raw_token=raw_token,
    )


async def load_auth_context(
    db: AsyncSession,
    raw_token: str,
    *,
    now: datetime | None = None,
) -> AuthenticatedContext | None:
    current_time = now or datetime.now(UTC)
    token_hash = hash_session_token(raw_token)

    auth_session = await db.scalar(
        select(AuthSession)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > current_time,
        )
        .options(
            joinedload(AuthSession.user).joinedload(User.telegram_identity),
        )
    )
    if auth_session is None:
        return None

    identity = auth_session.user.telegram_identity
    if identity is None:
        return None

    return AuthenticatedContext(
        session=auth_session,
        user=auth_session.user,
        identity=identity,
    )


async def revoke_auth_session(
    db: AsyncSession,
    auth_session: AuthSession,
    *,
    now: datetime | None = None,
) -> None:
    auth_session.revoked_at = now or datetime.now(UTC)
    await db.flush()
