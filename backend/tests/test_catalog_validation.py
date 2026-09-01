import uuid
from decimal import Decimal

import pytest

from app.modules.catalog.enums import AttributeDataType, FilterType
from app.modules.catalog.models import CategoryAttribute
from app.modules.catalog.service import (
    CatalogValidationError,
    validate_attribute_values,
)


def _attribute(
    key: str,
    data_type: AttributeDataType,
    *,
    category_id: uuid.UUID,
    required: bool = False,
    allowed_values: list[str] | None = None,
    validation_metadata: dict[str, object] | None = None,
) -> CategoryAttribute:
    return CategoryAttribute(
        id=uuid.uuid4(),
        category_id=category_id,
        key=key,
        label=key,
        data_type=data_type,
        required=required,
        filterable=False,
        searchable=False,
        card_visible=False,
        detail_visible=True,
        table_visible=False,
        excel_visible=True,
        sort_order=0,
        filter_type=FilterType.NONE,
        allowed_values=allowed_values,
        validation_metadata=validation_metadata,
        is_system=True,
    )


def test_valid_typed_values_are_prepared_without_losing_decimal_precision() -> None:
    category_id = uuid.uuid4()
    definitions = [
        _attribute("text", AttributeDataType.TEXT, category_id=category_id),
        _attribute("integer", AttributeDataType.INTEGER, category_id=category_id),
        _attribute("decimal", AttributeDataType.DECIMAL, category_id=category_id),
        _attribute("boolean", AttributeDataType.BOOLEAN, category_id=category_id),
        _attribute(
            "enum",
            AttributeDataType.ENUM,
            category_id=category_id,
            allowed_values=["A", "B"],
        ),
    ]

    result = validate_attribute_values(
        category_id,
        definitions,
        {
            "text": "  exact   text ",
            "integer": 10,
            "decimal": "12345.1234567890",
            "boolean": True,
            "enum": "A",
        },
    )

    by_key = {value.attribute.key: value for value in result}
    assert by_key["text"].text_value == "exact text"
    assert by_key["integer"].integer_value == 10
    assert by_key["decimal"].decimal_value == Decimal("12345.1234567890")
    assert by_key["boolean"].boolean_value is True
    assert by_key["enum"].enum_value == "A"


@pytest.mark.parametrize(
    ("data_type", "raw_value"),
    [
        (AttributeDataType.TEXT, 1),
        (AttributeDataType.INTEGER, "1"),
        (AttributeDataType.DECIMAL, 1.5),
        (AttributeDataType.BOOLEAN, 1),
        (AttributeDataType.ENUM, 1),
    ],
)
def test_wrong_attribute_type_is_rejected(
    data_type: AttributeDataType,
    raw_value: object,
) -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "value",
        data_type,
        category_id=category_id,
        allowed_values=["A"] if data_type == AttributeDataType.ENUM else None,
    )

    with pytest.raises(CatalogValidationError) as exc_info:
        validate_attribute_values(
            category_id,
            [attribute],
            {"value": raw_value},
        )

    assert exc_info.value.code == "attribute_type_mismatch"


def test_boolean_is_not_accepted_as_integer() -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "integer",
        AttributeDataType.INTEGER,
        category_id=category_id,
    )

    with pytest.raises(CatalogValidationError) as exc_info:
        validate_attribute_values(category_id, [attribute], {"integer": True})

    assert exc_info.value.code == "attribute_type_mismatch"


def test_unknown_and_cross_category_attributes_are_rejected() -> None:
    category_id = uuid.uuid4()
    other_category_id = uuid.uuid4()
    attribute = _attribute(
        "foreign",
        AttributeDataType.TEXT,
        category_id=other_category_id,
    )

    with pytest.raises(CatalogValidationError) as cross_category:
        validate_attribute_values(category_id, [attribute], {"foreign": "value"})
    assert cross_category.value.code == "cross_category_attribute"

    local_attribute = _attribute(
        "known",
        AttributeDataType.TEXT,
        category_id=category_id,
    )
    with pytest.raises(CatalogValidationError) as unknown:
        validate_attribute_values(category_id, [local_attribute], {"other": "value"})
    assert unknown.value.code == "unknown_attribute"


def test_required_missing_and_whitespace_only_values_are_rejected() -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "required_text",
        AttributeDataType.TEXT,
        category_id=category_id,
        required=True,
    )

    with pytest.raises(CatalogValidationError) as missing:
        validate_attribute_values(category_id, [attribute], {})
    assert missing.value.code == "required_attribute_missing"

    with pytest.raises(CatalogValidationError) as blank:
        validate_attribute_values(
            category_id,
            [attribute],
            {"required_text": " \t "},
        )
    assert blank.value.code == "required_attribute_missing"


def test_invalid_enum_value_is_rejected() -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "enum",
        AttributeDataType.ENUM,
        category_id=category_id,
        allowed_values=["A", "B"],
    )

    with pytest.raises(CatalogValidationError) as exc_info:
        validate_attribute_values(category_id, [attribute], {"enum": "C"})

    assert exc_info.value.code == "attribute_enum_invalid"


def test_numeric_validation_metadata_is_applied() -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "positive",
        AttributeDataType.DECIMAL,
        category_id=category_id,
        validation_metadata={"min": "0.1", "max": "10.5"},
    )

    with pytest.raises(CatalogValidationError) as too_small:
        validate_attribute_values(category_id, [attribute], {"positive": "0.01"})
    assert too_small.value.code == "attribute_below_minimum"

    with pytest.raises(CatalogValidationError) as too_large:
        validate_attribute_values(category_id, [attribute], {"positive": "11"})
    assert too_large.value.code == "attribute_above_maximum"
