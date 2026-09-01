from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.config import Settings
from app.modules.auth.dependencies import Authenticated, DbSession
from app.modules.auth.schemas import (
    AuthStateOut,
    AuthUserOut,
    SupportContactOut,
    TelegramAuthRequest,
)
from app.modules.auth.service import (
    issue_auth_session,
    revoke_auth_session,
    upsert_telegram_identity,
)
from app.modules.auth.telegram import TelegramInitDataError, validate_telegram_init_data
from app.modules.identity.models import TelegramIdentity, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _state_response(
    user: User,
    identity: TelegramIdentity,
    settings: Settings,
) -> AuthStateOut:
    return AuthStateOut(
        user=AuthUserOut(
            id=user.id,
            telegram_user_id=identity.telegram_user_id,
            username=identity.username,
            first_name=identity.first_name,
            last_name=identity.last_name,
            role=user.role,
            access_status=user.access_status,
        ),
        support=SupportContactOut(
            username=settings.support_telegram_username,
            url=settings.support_telegram_url,
        ),
    )


@router.post("/telegram", response_model=AuthStateOut)
async def authenticate_with_telegram(
    payload: TelegramAuthRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> AuthStateOut:
    settings: Settings = request.app.state.settings
    bot_token = settings.telegram_bot_token_value
    if bot_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram authentication unavailable",
        )

    try:
        validated = validate_telegram_init_data(
            payload.init_data,
            bot_token=bot_token,
            max_age_seconds=settings.telegram_init_data_max_age_seconds,
        )
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Telegram init data",
        ) from exc

    async with db.begin():
        user, identity = await upsert_telegram_identity(db, validated, settings)
        issued = await issue_auth_session(
            db,
            user,
            ttl_seconds=settings.auth_session_ttl_seconds,
        )

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=issued.raw_token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return _state_response(user, identity, settings)


@router.get("/me", response_model=AuthStateOut)
async def get_me(
    request: Request,
    response: Response,
    authenticated: Authenticated,
) -> AuthStateOut:
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    return _state_response(authenticated.user, authenticated.identity, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    authenticated: Authenticated,
) -> None:
    await revoke_auth_session(db, authenticated.session)
    await db.commit()

    settings: Settings = request.app.state.settings
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.app_env == "production",
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
