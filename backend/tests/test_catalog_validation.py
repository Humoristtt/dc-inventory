import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.catalog.enums import AttributeDataType, FilterType
from app.modules.catalog.models import CategoryAttribute
from app.modules.catalog.schemas import ItemCreate
from app.modules.catalog.service import (
    SFP_CATEGORY_ID,
    CatalogSchemaError,
    CatalogValidationError,
    normalize_comparison,
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


def test_text_metadata_can_preserve_source_profile_whitespace() -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "reach_profile",
        AttributeDataType.TEXT,
        category_id=category_id,
        validation_metadata={"max_length": 2000, "preserve_whitespace": True},
    )
    source_profile = "  OM3: до 70 м\nOM4: до 100 м  "

    result = validate_attribute_values(
        category_id,
        [attribute],
        {"reach_profile": source_profile},
    )

    assert result[0].text_value == "OM3: до 70 м\nOM4: до 100 м"


def test_text_preserve_whitespace_metadata_requires_boolean() -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "profile",
        AttributeDataType.TEXT,
        category_id=category_id,
        validation_metadata={"preserve_whitespace": "yes"},
    )

    with pytest.raises(CatalogSchemaError):
        validate_attribute_values(category_id, [attribute], {"profile": "value"})


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


@pytest.mark.parametrize(
    "raw_value",
    [
        "99999999999999999999.1234567890",
        Decimal("1E+19"),
        Decimal("0E+100"),
    ],
)
def test_decimal_values_within_numeric_30_10_storage_bounds_are_accepted(
    raw_value: str | Decimal,
) -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "decimal",
        AttributeDataType.DECIMAL,
        category_id=category_id,
    )

    result = validate_attribute_values(
        category_id,
        [attribute],
        {"decimal": raw_value},
    )

    assert result[0].decimal_value == Decimal(raw_value)


@pytest.mark.parametrize(
    ("raw_value", "error_code"),
    [
        ("100000000000000000000", "decimal_precision_exceeded"),
        ("0.12345678901", "decimal_scale_exceeded"),
    ],
)
def test_decimal_values_outside_numeric_30_10_storage_bounds_are_rejected(
    raw_value: str,
    error_code: str,
) -> None:
    category_id = uuid.uuid4()
    attribute = _attribute(
        "decimal",
        AttributeDataType.DECIMAL,
        category_id=category_id,
    )

    with pytest.raises(CatalogValidationError) as exc_info:
        validate_attribute_values(
            category_id,
            [attribute],
            {"decimal": raw_value},
        )

    assert exc_info.value.code == error_code


def test_normalize_comparison_checks_casefolded_storage_length() -> None:
    within_limit = "ß" * 64
    assert (
        normalize_comparison(
            within_limit,
            field="internal_code",
            max_length=128,
        )
        == "ss" * 64
    )

    with pytest.raises(CatalogValidationError) as exc_info:
        normalize_comparison(
            "ß" * 65,
            field="internal_code",
            max_length=128,
        )

    assert exc_info.value.code == "internal_code_too_long"


@pytest.mark.parametrize(
    "datasheet_url",
    [
        "javascript:alert(1)",
        "ftp://example.com/spec.pdf",
        "not a URL",
    ],
)
def test_item_datasheet_url_rejects_non_http_link_semantics(
    datasheet_url: str,
) -> None:
    with pytest.raises(ValidationError):
        ItemCreate(
            category_key="nic",
            name="Network adapter",
            datasheet_url=datasheet_url,
        )


def test_item_datasheet_url_accepts_valid_http_and_https_links() -> None:
    for datasheet_url in (
        "http://example.com/spec",
        "https://example.com/spec.pdf?revision=2#details",
    ):
        payload = ItemCreate(
            category_key="nic",
            name="Network adapter",
            datasheet_url=datasheet_url,
        )
        assert payload.datasheet_url == datasheet_url

@pytest.mark.parametrize(
    (
        "profile_key",
        "profile",
        "scalar_key",
        "scalar_type",
        "scalar",
    ),
    [
        (
            "speed_profile",
            "4/8/16G FC",
            "speed_mbps",
            AttributeDataType.INTEGER,
            16000,
        ),
        (
            "speed_profile",
            "8/16/32G FC",
            "speed_mbps",
            AttributeDataType.INTEGER,
            32000,
        ),
        (
            "reach_profile",
            "OM2: до 35 м\nOM3: до 100 м\nOM4: до 125 м",
            "reach_m",
            AttributeDataType.INTEGER,
            125,
        ),
        (
            "reach_profile",
            (
                "OM3: 30 м без RS-FEC / 70 м с RS-FEC\n"
                "OM4: 40 м без RS-FEC / 100 м с RS-FEC"
            ),
            "reach_m",
            AttributeDataType.INTEGER,
            100,
        ),
        (
            "wavelength_profile",
            "1310 нм",
            "nominal_wavelength_nm",
            AttributeDataType.DECIMAL,
            Decimal("1310"),
        ),
    ],
)
def test_sfp_profile_scalar_pairs_match_authoritative_contract(
    profile_key: str,
    profile: str,
    scalar_key: str,
    scalar_type: AttributeDataType,
    scalar: int | Decimal,
) -> None:
    category_id = SFP_CATEGORY_ID
    definitions = [
        _attribute(
            profile_key,
            AttributeDataType.TEXT,
            category_id=category_id,
            validation_metadata={
                "preserve_whitespace": True,
                "max_length": 2000,
            },
        ),
        _attribute(
            scalar_key,
            scalar_type,
            category_id=category_id,
        ),
    ]

    result = validate_attribute_values(
        category_id,
        definitions,
        {
            profile_key: profile,
            scalar_key: scalar,
        },
    )

    assert len(result) == 2


@pytest.mark.parametrize(
    (
        "profile_key",
        "profile",
        "scalar_key",
        "scalar_type",
        "scalar",
    ),
    [
        (
            "speed_profile",
            "10/25 Гбит/с",
            "speed_mbps",
            AttributeDataType.INTEGER,
            10000,
        ),
        (
            "reach_profile",
            "до 20 км",
            "reach_m",
            AttributeDataType.INTEGER,
            10000,
        ),
        (
            "wavelength_profile",
            "850 нм",
            "nominal_wavelength_nm",
            AttributeDataType.DECIMAL,
            Decimal("1310"),
        ),
        (
            "wavelength_profile",
            "1271 / 1291 / 1311 / 1331 нм",
            "nominal_wavelength_nm",
            AttributeDataType.DECIMAL,
            Decimal("1271"),
        ),
    ],
)
def test_sfp_profile_scalar_contradictions_are_rejected(
    profile_key: str,
    profile: str,
    scalar_key: str,
    scalar_type: AttributeDataType,
    scalar: int | Decimal,
) -> None:
    category_id = SFP_CATEGORY_ID
    definitions = [
        _attribute(
            profile_key,
            AttributeDataType.TEXT,
            category_id=category_id,
            validation_metadata={
                "preserve_whitespace": True,
                "max_length": 2000,
            },
        ),
        _attribute(
            scalar_key,
            scalar_type,
            category_id=category_id,
        ),
    ]

    with pytest.raises(CatalogValidationError) as exc_info:
        validate_attribute_values(
            category_id,
            definitions,
            {
                profile_key: profile,
                scalar_key: scalar,
            },
        )

    assert exc_info.value.code == "profile_scalar_mismatch"


def test_sfp_unknown_profile_with_scalar_is_rejected() -> None:
    category_id = SFP_CATEGORY_ID
    definitions = [
        _attribute(
            "speed_profile",
            AttributeDataType.TEXT,
            category_id=category_id,
        ),
        _attribute(
            "speed_mbps",
            AttributeDataType.INTEGER,
            category_id=category_id,
        ),
    ]

    with pytest.raises(CatalogValidationError) as exc_info:
        validate_attribute_values(
            category_id,
            definitions,
            {
                "speed_profile": "50 Гбит/с experimental",
                "speed_mbps": 50000,
            },
        )

    assert exc_info.value.code == "profile_scalar_unverifiable"


def test_sfp_unknown_optional_profile_without_scalar_is_preserved() -> None:
    category_id = SFP_CATEGORY_ID
    definitions = [
        _attribute(
            "reach_profile",
            AttributeDataType.TEXT,
            category_id=category_id,
            validation_metadata={"preserve_whitespace": True},
        ),
        _attribute(
            "reach_m",
            AttributeDataType.INTEGER,
            category_id=category_id,
        ),
    ]

    result = validate_attribute_values(
        category_id,
        definitions,
        {
            "reach_profile": "Vendor-specific conditional reach",
        },
    )

    assert result[0].text_value == "Vendor-specific conditional reach"

def test_sfp_contract_is_not_applied_to_other_categories() -> None:
    category_id = uuid.uuid4()
    definitions = [
        _attribute(
            "speed_profile",
            AttributeDataType.TEXT,
            category_id=category_id,
        ),
        _attribute(
            "speed_mbps",
            AttributeDataType.INTEGER,
            category_id=category_id,
        ),
    ]

    result = validate_attribute_values(
        category_id,
        definitions,
        {
            "speed_profile": "Independent category semantics",
            "speed_mbps": 12345,
        },
    )

    assert len(result) == 2
