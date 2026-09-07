from enum import StrEnum


class LocationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class LocationType(StrEnum):
    WAREHOUSE = "WAREHOUSE"
    DATACENTER = "DATACENTER"


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    RETURN = "RETURN"
    TRANSFER = "TRANSFER"
    WRITE_OFF = "WRITE_OFF"
    CORRECTION = "CORRECTION"
    REVERSAL = "REVERSAL"
