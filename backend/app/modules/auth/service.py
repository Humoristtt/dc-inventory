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
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)
from app.modules.identity.models import AccessRequest, TelegramIdentity, User

SESSION_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class IssuedAuthSession:
    session: AuthSession
    raw_token: str


@dataclass(frozen=True, slots=True)
class AuthenticatedContext:
    session: AuthSession
    user: User
    identity: TelegramIdentity


def hash_session_token(raw_token: str) -> bytes:
    return hashlib.sha256(raw_token.encode("utf-8")).digest()


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

    bootstrap_admin = settings.admin_telegram_user_id == telegram_user_id

    if identity is None:
        user = User(
            role=UserRole.ADMIN if bootstrap_admin else UserRole.USER,
            access_status=(
                UserAccessStatus.APPROVED
                if bootstrap_admin
                else UserAccessStatus.PENDING
            ),
            approved_at=current_time if bootstrap_admin else None,
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

    # Configured bootstrap admin является постоянным recovery/admin identity.
    if bootstrap_admin:
        user.role = UserRole.ADMIN
        user.access_status = UserAccessStatus.APPROVED
        if user.approved_at is None:
            user.approved_at = current_time

        pending_statement = (
            select(AccessRequest)
            .where(
                AccessRequest.user_id == user.id,
                AccessRequest.status == AccessRequestStatus.PENDING,
            )
            .with_for_update()
        )
        pending_result = await db.scalars(pending_statement)
        pending_request = pending_result.first()
        if pending_request is not None:
            pending_request.status = AccessRequestStatus.APPROVED
            pending_request.decided_at = current_time
            pending_request.decided_by_user_id = user.id
            pending_request.decision_note = "bootstrap admin configuration"

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
    raw_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        created_at=current_time,
        last_seen_at=current_time,
        expires_at=current_time + timedelta(seconds=ttl_seconds),
    )
    db.add(session)
    await db.flush()
    return IssuedAuthSession(session=session, raw_token=raw_token)


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
