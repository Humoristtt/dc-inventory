import pytest
from pydantic import BaseModel, ValidationError

from app.modules.auth.schemas import TelegramAuthRequest
from app.modules.identity.admin_schemas import (
    AdminUserAccessRequestDecision,
    AdminUserPatch,
    AdminUserRolePatch,
)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            TelegramAuthRequest,
            {"init_data": "test"},
        ),
        (
            AdminUserPatch,
            {"access_status": "APPROVED"},
        ),
        (
            AdminUserAccessRequestDecision,
            {"decision": "APPROVE"},
        ),
        (
            AdminUserRolePatch,
            {"role": "ENGINEER"},
        ),
    ],
)
def test_external_mutation_request_models_forbid_unknown_fields(
    model: type[BaseModel],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(
            {
                **payload,
                "unexpected_field": "must-fail",
            }
        )
