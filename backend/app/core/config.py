from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=5, ge=0, le=20)
    database_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_statement_timeout_seconds: int = Field(default=30, ge=1, le=300)
    database_lock_timeout_seconds: int = Field(default=5, ge=1, le=60)

    model_config = SettingsConfigDict(
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
