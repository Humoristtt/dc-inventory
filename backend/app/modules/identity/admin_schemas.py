from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.identity.enums import UserAccessStatus, UserRole


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    is_recovery_identity: bool


class AdminUserPageOut(BaseModel):
    items: list[AdminUserOut]
    total: int


class AdminUserPatch(StrictRequestModel):
    access_status: UserAccessStatus


class AdminUserAccessRequestDecision(StrictRequestModel):
    decision: Literal["APPROVE", "REJECT"]


class AdminUserRolePatch(StrictRequestModel):
    role: UserRole


class UserAccessEventOut(BaseModel):
    id: UUID
    actor_user_id: UUID
    actor_display_name: str
    target_user_id: UUID
    before_access_status: UserAccessStatus
    after_access_status: UserAccessStatus
    occurred_at: datetime


class UserAccessEventPageOut(BaseModel):
    items: list[UserAccessEventOut]
    total: int


class UserRoleEventOut(BaseModel):
    id: UUID
    actor_user_id: UUID
    actor_display_name: str
    target_user_id: UUID
    before_role: UserRole
    after_role: UserRole
    occurred_at: datetime


class UserRoleEventPageOut(BaseModel):
    items: list[UserRoleEventOut]
    total: int
