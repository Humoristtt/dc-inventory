from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.db.engine import create_engine


def validate_backend_runtime_config(settings: Settings) -> None:
    if settings.app_env != "production":
        return

    missing: list[str] = []

    if settings.telegram_bot_token_value is None:
        missing.append("TELEGRAM_BOT_TOKEN")

    if settings.admin_telegram_user_id is None:
        missing.append("ADMIN_TELEGRAM_USER_ID")

    if settings.telegram_webhook_secret_value is None:
        missing.append("TELEGRAM_WEBHOOK_SECRET")

    if missing:
        raise RuntimeError(
            "production backend configuration is incomplete: "
            + ", ".join(missing)
        )

    web_app_url = settings.telegram_web_app_url

    if web_app_url != web_app_url.strip():
        raise RuntimeError(
            "TELEGRAM_WEB_APP_URL must not contain surrounding whitespace"
        )

    try:
        parsed = urlsplit(web_app_url)
        port = parsed.port
    except ValueError as error:
        raise RuntimeError(
            "TELEGRAM_WEB_APP_URL must be a valid absolute HTTPS URL"
        ) from error

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise RuntimeError(
            "TELEGRAM_WEB_APP_URL must be an absolute HTTPS origin URL "
            "without path, query, or fragment"
        )


def _trusted_hosts(settings: Settings) -> list[str]:
    if settings.app_env != "production":
        return ["*"]

    hostname = urlsplit(settings.telegram_web_app_url).hostname
    if hostname is None:
        raise RuntimeError(
            "TELEGRAM_WEB_APP_URL hostname is required for trusted hosts"
        )

    return [
        hostname.lower(),
        "127.0.0.1",
        "localhost",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    app.state.db_engine = engine

    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    validate_backend_runtime_config(runtime_settings)
    docs_enabled = runtime_settings.app_env != "production"

    application = FastAPI(
        title="Инвентаризация оборудования ЦОД",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if docs_enabled else None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        redoc_url=None,
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_trusted_hosts(runtime_settings),
        www_redirect=False,
    )
    application.state.settings = runtime_settings
    application.include_router(api_router)

    return application


app = create_app()
