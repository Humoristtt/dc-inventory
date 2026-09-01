from enum import StrEnum


class AccountingMode(StrEnum):
    QUANTITY = "QUANTITY"
    SERIAL = "SERIAL"


class ItemStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class AttributeDataType(StrEnum):
    TEXT = "TEXT"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"


class FilterType(StrEnum):
    NONE = "NONE"
    EXACT = "EXACT"
    RANGE = "RANGE"
