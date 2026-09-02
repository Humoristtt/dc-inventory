from enum import StrEnum


class LocationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class InventoryUnitState(StrEnum):
    STORED = "STORED"
    ISSUED = "ISSUED"
    WRITTEN_OFF = "WRITTEN_OFF"
    VOIDED = "VOIDED"


class MovementType(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    RETURN = "RETURN"
    TRANSFER = "TRANSFER"
    WRITE_OFF = "WRITE_OFF"
    CORRECTION = "CORRECTION"
    REVERSAL = "REVERSAL"
