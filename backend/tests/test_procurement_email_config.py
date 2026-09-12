import pytest

from app.core.config import Settings
from app.modules.procurement.email import validate_email_worker_config

DATABASE_URL = "postgresql+asyncpg://dc_inventory:test@postgres:5432/dc_inventory"


def email_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": DATABASE_URL,
        "microsoft_graph_tenant_id": "tenant",
        "microsoft_graph_client_id": "client",
        "microsoft_graph_client_secret": "secret",
        "microsoft_graph_sender": "inventory@example.test",
        "microsoft_graph_timeout_seconds": 15,
        "email_worker_claim_ttl_seconds": 60,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_email_worker_complete_configuration_is_accepted() -> None:
    validate_email_worker_config(email_settings())


@pytest.mark.parametrize(
    "field",
    [
        "microsoft_graph_tenant_id",
        "microsoft_graph_client_id",
        "microsoft_graph_client_secret",
        "microsoft_graph_sender",
    ],
)
def test_email_worker_requires_graph_configuration(field: str) -> None:
    settings = email_settings(**{field: ""})

    with pytest.raises(
        RuntimeError,
        match="Microsoft Graph email worker configuration is incomplete",
    ):
        validate_email_worker_config(settings)


def test_email_worker_rejects_unsafe_claim_ttl() -> None:
    settings = email_settings(
        microsoft_graph_timeout_seconds=30,
        email_worker_claim_ttl_seconds=60,
    )

    with pytest.raises(
        RuntimeError,
        match="EMAIL_WORKER_CLAIM_TTL_SECONDS",
    ):
        validate_email_worker_config(settings)
