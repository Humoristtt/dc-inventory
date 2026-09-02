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


class Availability(StrEnum):
    ANY = "ANY"
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class ItemSort(StrEnum):
    NAME = "name"
    MANUFACTURER = "manufacturer"
    AVAILABLE = "available"
    TOTAL = "total"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"
