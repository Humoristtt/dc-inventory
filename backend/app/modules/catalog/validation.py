from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

from app.modules.catalog.enums import AttributeDataType
from app.modules.catalog.models import CategoryAttribute

MAX_DECIMAL_PRECISION = 30
MAX_DECIMAL_SCALE = 10
MAX_DECIMAL_INTEGRAL_DIGITS = MAX_DECIMAL_PRECISION - MAX_DECIMAL_SCALE
MIN_SAFE_INTEGER = -(2**53 - 1)
MAX_SAFE_INTEGER = 2**53 - 1


class CatalogError(RuntimeError):
    code = "catalog_error"


class CatalogValidationError(CatalogError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CatalogNotFoundError(CatalogError):
    code = "catalog_not_found"


class CatalogConflictError(CatalogError):
    code = "catalog_conflict"


class CatalogItemInUseError(CatalogConflictError):
    code = "catalog_item_in_use"


class CatalogSchemaError(CatalogError):
    code = "catalog_schema_invalid"


@dataclass(frozen=True, slots=True)
class PreparedAttributeValue:
    attribute: CategoryAttribute
    text_value: str | None = None
    integer_value: int | None = None
    decimal_value: Decimal | None = None
    boolean_value: bool | None = None
    enum_value: str | None = None


def normalize_inline_text(value: str, *, field: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise CatalogValidationError(
            f"{field}_required",
            f"{field} must not be blank",
        )
    if len(normalized) > max_length:
        raise CatalogValidationError(
            f"{field}_too_long",
            f"{field} exceeds {max_length} characters",
        )
    return normalized


def normalize_optional_inline_text(
    value: str | None,
    *,
    field: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise CatalogValidationError(
            f"{field}_too_long",
            f"{field} exceeds {max_length} characters",
        )
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_comparison(
    value: str,
    *,
    field: str | None = None,
    max_length: int | None = None,
) -> str:
    normalized = " ".join(value.split()).casefold()
    if max_length is not None and len(normalized) > max_length:
        error_field = field or "normalized_value"
        raise CatalogValidationError(
            f"{error_field}_too_long",
            f"{error_field} normalized value exceeds {max_length} characters",
        )
    return normalized


def _normalize_category_key(value: str) -> str:
    return normalize_inline_text(value, field="category_key", max_length=64).casefold()


def _numeric_metadata(
    attribute: CategoryAttribute,
    key: str,
) -> Decimal | None:
    metadata = attribute.validation_metadata
    if metadata is None or key not in metadata:
        return None
    raw = metadata[key]
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        raise CatalogSchemaError(f"attribute {attribute.key} has invalid {key} metadata")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise CatalogSchemaError(f"attribute {attribute.key} has invalid {key} metadata") from exc
    if not value.is_finite():
        raise CatalogSchemaError(f"attribute {attribute.key} has non-finite {key} metadata")
    return value


def _validate_numeric_bounds(
    attribute: CategoryAttribute,
    value: Decimal,
) -> None:
    minimum = _numeric_metadata(attribute, "min")
    maximum = _numeric_metadata(attribute, "max")
    if minimum is not None and value < minimum:
        raise CatalogValidationError(
            "attribute_below_minimum",
            f"attribute {attribute.key} must be at least {minimum}",
        )
    if maximum is not None and value > maximum:
        raise CatalogValidationError(
            "attribute_above_maximum",
            f"attribute {attribute.key} must be at most {maximum}",
        )


def _validate_decimal_storage(attribute: CategoryAttribute, value: Decimal) -> None:
    _, digits, exponent = value.as_tuple()
    exponent = cast(int, exponent)
    fractional_digits = max(-exponent, 0)
    integer_digits = 0 if value.is_zero() else max(len(digits) + exponent, 0)
    if fractional_digits > MAX_DECIMAL_SCALE:
        raise CatalogValidationError(
            "decimal_scale_exceeded",
            f"attribute {attribute.key} supports at most {MAX_DECIMAL_SCALE} decimal places",
        )
    if integer_digits > MAX_DECIMAL_INTEGRAL_DIGITS:
        raise CatalogValidationError(
            "decimal_precision_exceeded",
            f"attribute {attribute.key} supports at most "
            f"{MAX_DECIMAL_INTEGRAL_DIGITS} integral digits",
        )


def _prepare_attribute_value(
    attribute: CategoryAttribute,
    raw_value: object,
) -> PreparedAttributeValue | None:
    if attribute.data_type == AttributeDataType.TEXT:
        if not isinstance(raw_value, str):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires TEXT",
            )
        metadata = attribute.validation_metadata or {}
        preserve_whitespace = metadata.get("preserve_whitespace", False)
        if not isinstance(preserve_whitespace, bool):
            raise CatalogSchemaError(
                f"attribute {attribute.key} has invalid preserve_whitespace metadata"
            )
        value = raw_value.strip() if preserve_whitespace else " ".join(raw_value.split())
        if not value:
            if attribute.required:
                raise CatalogValidationError(
                    "required_attribute_missing",
                    f"required attribute {attribute.key} must not be blank",
                )
            return None
        max_length = metadata.get("max_length")
        if max_length is not None:
            if isinstance(max_length, bool) or not isinstance(max_length, int):
                raise CatalogSchemaError(
                    f"attribute {attribute.key} has invalid max_length metadata"
                )
            if len(value) > max_length:
                raise CatalogValidationError(
                    "attribute_too_long",
                    f"attribute {attribute.key} exceeds {max_length} characters",
                )
        return PreparedAttributeValue(attribute=attribute, text_value=value)

    if attribute.data_type == AttributeDataType.INTEGER:
        if type(raw_value) is not int:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires INTEGER",
            )
        integer_value = raw_value
        if not MIN_SAFE_INTEGER <= integer_value <= MAX_SAFE_INTEGER:
            raise CatalogValidationError(
                "integer_out_of_range",
                f"attribute {attribute.key} is outside the exact JSON integer range",
            )
        _validate_numeric_bounds(attribute, Decimal(integer_value))
        return PreparedAttributeValue(
            attribute=attribute,
            integer_value=integer_value,
        )

    if attribute.data_type == AttributeDataType.DECIMAL:
        if isinstance(raw_value, (bool, float)):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires an exact decimal string or integer",
            )
        if not isinstance(raw_value, (Decimal, int, str)):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires DECIMAL",
            )
        if isinstance(raw_value, str) and not raw_value.strip():
            if attribute.required:
                raise CatalogValidationError(
                    "required_attribute_missing",
                    f"required attribute {attribute.key} must not be blank",
                )
            return None
        try:
            decimal_value = (
                raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value).strip())
            )
        except InvalidOperation as exc:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires DECIMAL",
            ) from exc
        if not decimal_value.is_finite():
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires a finite DECIMAL",
            )
        _validate_decimal_storage(attribute, decimal_value)
        _validate_numeric_bounds(attribute, decimal_value)
        return PreparedAttributeValue(
            attribute=attribute,
            decimal_value=decimal_value,
        )

    if attribute.data_type == AttributeDataType.BOOLEAN:
        if type(raw_value) is not bool:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires BOOLEAN",
            )
        return PreparedAttributeValue(
            attribute=attribute,
            boolean_value=raw_value,
        )

    if attribute.data_type == AttributeDataType.ENUM:
        if not isinstance(raw_value, str):
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires ENUM",
            )
        enum_value = " ".join(raw_value.split())
        if not enum_value:
            if attribute.required:
                raise CatalogValidationError(
                    "required_attribute_missing",
                    f"required attribute {attribute.key} must not be blank",
                )
            return None
        allowed_values = attribute.allowed_values
        if (
            not isinstance(allowed_values, list)
            or not allowed_values
            or any(not isinstance(value, str) for value in allowed_values)
        ):
            raise CatalogSchemaError(f"attribute {attribute.key} has invalid ENUM allowed_values")
        if enum_value not in allowed_values:
            raise CatalogValidationError(
                "attribute_enum_invalid",
                f"attribute {attribute.key} must be one of its allowed values",
            )
        return PreparedAttributeValue(
            attribute=attribute,
            enum_value=enum_value,
        )

    raise CatalogSchemaError(f"attribute {attribute.key} has unsupported data type")


def prepare_attribute_filter_value(
    attribute: CategoryAttribute,
    raw_value: str,
) -> str | int | Decimal | bool:
    """Parse one query-string value through the canonical attribute validator."""
    candidate: object
    if attribute.data_type == AttributeDataType.INTEGER:
        stripped = raw_value.strip()
        if re.fullmatch(r"[+-]?\d+", stripped) is None:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires INTEGER",
            )
        try:
            candidate = int(stripped)
        except ValueError as error:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires INTEGER",
            ) from error
    elif attribute.data_type == AttributeDataType.BOOLEAN:
        normalized = raw_value.strip().casefold()
        if normalized not in {"true", "false"}:
            raise CatalogValidationError(
                "attribute_type_mismatch",
                f"attribute {attribute.key} requires true or false",
            )
        candidate = normalized == "true"
    else:
        candidate = raw_value

    prepared = _prepare_attribute_value(attribute, candidate)
    if prepared is None:
        raise CatalogValidationError(
            "attribute_type_mismatch",
            f"attribute {attribute.key} requires a value",
        )
    if attribute.data_type == AttributeDataType.TEXT:
        assert prepared.text_value is not None
        return prepared.text_value
    if attribute.data_type == AttributeDataType.INTEGER:
        assert prepared.integer_value is not None
        return prepared.integer_value
    if attribute.data_type == AttributeDataType.DECIMAL:
        assert prepared.decimal_value is not None
        return prepared.decimal_value
    if attribute.data_type == AttributeDataType.BOOLEAN:
        assert prepared.boolean_value is not None
        return prepared.boolean_value
    if attribute.data_type == AttributeDataType.ENUM:
        assert prepared.enum_value is not None
        return prepared.enum_value
    raise CatalogSchemaError(f"attribute {attribute.key} has unsupported data type")


def validate_attribute_values(
    category_id: uuid.UUID,
    definitions: Sequence[CategoryAttribute],
    supplied_values: Mapping[str, object],
) -> list[PreparedAttributeValue]:
    for attribute in definitions:
        if attribute.category_id != category_id:
            raise CatalogValidationError(
                "cross_category_attribute",
                f"attribute {attribute.key} belongs to another category",
            )

    by_key = {attribute.key: attribute for attribute in definitions}
    unknown_keys = sorted(set(supplied_values) - set(by_key))
    if unknown_keys:
        raise CatalogValidationError(
            "unknown_attribute",
            f"unknown category attributes: {', '.join(unknown_keys)}",
        )

    missing_required = sorted(
        attribute.key
        for attribute in definitions
        if attribute.required and attribute.key not in supplied_values
    )
    if missing_required:
        raise CatalogValidationError(
            "required_attribute_missing",
            f"missing required attributes: {', '.join(missing_required)}",
        )

    prepared: list[PreparedAttributeValue] = []
    for key, raw_value in supplied_values.items():
        value = _prepare_attribute_value(by_key[key], raw_value)
        if value is not None:
            prepared.append(value)

    return prepared
