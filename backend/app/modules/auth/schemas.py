from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.policy import Capability


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelegramAuthRequest(StrictRequestModel):
    init_data: str = Field(min_length=1, max_length=16_384)


class SupportContactOut(BaseModel):
    username: str
    url: str


class AuthUserOut(BaseModel):
    id: UUID
    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    role: UserRole
    capabilities: list[Capability]
    access_status: UserAccessStatus


class AuthStateOut(BaseModel):
    user: AuthUserOut
    support: SupportContactOut
