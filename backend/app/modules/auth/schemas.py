from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.identity.enums import UserAccessStatus, UserRole


class TelegramAuthRequest(BaseModel):
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
    access_status: UserAccessStatus


class AuthStateOut(BaseModel):
    user: AuthUserOut
    support: SupportContactOut
