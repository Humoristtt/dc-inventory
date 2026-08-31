from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.db.engine import create_engine


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
    docs_enabled = runtime_settings.app_env != "production"

    application = FastAPI(
        title="Инвентаризация оборудования ЦОД",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if docs_enabled else None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        redoc_url=None,
    )
    application.state.settings = runtime_settings
    application.include_router(api_router)

    return application


app = create_app()
