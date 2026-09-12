from enum import StrEnum


class UserRole(StrEnum):
    ENGINEER = "ENGINEER"
    SENIOR_ENGINEER = "SENIOR_ENGINEER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    OWNER = "OWNER"


class UserAccessStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class AccessRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
