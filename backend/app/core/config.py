from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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

    migration_statement_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
    )
    migration_lock_timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
    )

    telegram_bot_token: SecretStr | None = None
    telegram_init_data_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    admin_telegram_user_id: int | None = Field(default=None, gt=0, le=2**52)
    support_telegram_username: str = Field(
        default="Humoristttt",
        pattern=r"^[A-Za-z][A-Za-z0-9_]{4,31}$",
    )
    auth_session_ttl_seconds: int = Field(default=43_200, ge=300, le=2_592_000)
    auth_cookie_name: str = Field(
        default="dc_inventory_session",
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
    )

    telegram_webhook_secret: SecretStr | None = None
    telegram_web_app_url: str = "https://app.spik-inventory.ru"
    telegram_gateway_url: str | None = None
    telegram_gateway_secret: SecretStr | None = None
    telegram_gateway_timeout_seconds: int = Field(default=10, ge=1, le=60)
    notification_worker_poll_seconds: int = Field(default=2, ge=1, le=60)
    notification_worker_claim_ttl_seconds: int = Field(default=60, ge=10, le=600)
    notification_worker_batch_size: int = Field(default=10, ge=1, le=100)
    notification_worker_max_attempts: int = Field(default=8, ge=1, le=20)

    maintenance_worker_poll_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
    )
    maintenance_retention_batch_size: int = Field(
        default=1000,
        ge=1,
        le=5000,
    )
    auth_session_retention_days: int = Field(
        default=7,
        ge=1,
        le=365,
    )
    telegram_update_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
    )
    notification_outbox_retention_days: int = Field(
        default=90,
        ge=1,
        le=730,
    )
    access_callback_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
    )

    @field_validator("admin_telegram_user_id", mode="before")
    @classmethod
    def empty_admin_telegram_user_id_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def telegram_bot_token_value(self) -> str | None:
        if self.telegram_bot_token is None:
            return None
        value = self.telegram_bot_token.get_secret_value().strip()
        return value or None

    @property
    def telegram_webhook_secret_value(self) -> str | None:
        if self.telegram_webhook_secret is None:
            return None
        value = self.telegram_webhook_secret.get_secret_value().strip()
        return value or None

    @property
    def telegram_gateway_url_value(self) -> str | None:
        if self.telegram_gateway_url is None:
            return None
        value = self.telegram_gateway_url.strip().rstrip("/")
        return value or None

    @property
    def telegram_gateway_secret_value(self) -> str | None:
        if self.telegram_gateway_secret is None:
            return None
        value = self.telegram_gateway_secret.get_secret_value().strip()
        return value or None

    @property
    def support_telegram_url(self) -> str:
        return f"https://t.me/{self.support_telegram_username}"

    model_config = SettingsConfigDict(
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
