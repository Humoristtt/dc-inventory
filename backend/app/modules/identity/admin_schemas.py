from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.identity.enums import UserAccessStatus, UserRole


class AdminUserOut(BaseModel):
    id: UUID
    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    role: UserRole
    access_status: UserAccessStatus
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None


class AdminUserPageOut(BaseModel):
    items: list[AdminUserOut]
    total: int


class AdminUserPatch(BaseModel):
    access_status: UserAccessStatus


class UserAccessEventOut(BaseModel):
    id: UUID
    actor_user_id: UUID
    target_user_id: UUID
    before_access_status: UserAccessStatus
    after_access_status: UserAccessStatus
    occurred_at: datetime


class UserAccessEventPageOut(BaseModel):
    items: list[UserAccessEventOut]
    total: int
