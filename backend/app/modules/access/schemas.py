from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus


class AccessRequestOut(BaseModel):
    id: UUID
    status: AccessRequestStatus
    requested_at: datetime


class AccessStateOut(BaseModel):
    access_status: UserAccessStatus
    request: AccessRequestOut | None
