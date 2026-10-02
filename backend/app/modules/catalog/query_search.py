from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sqlalchemy import (
    case,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.sql.elements import ColumnElement

from app.modules.catalog.models import (
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.catalog.query_types import (
    CatalogQuerySpec,
)
from app.modules.catalog.validation import (
    MAX_DECIMAL_INTEGRAL_DIGITS,
    MAX_DECIMAL_SCALE,
    MAX_SAFE_INTEGER,
    MIN_SAFE_INTEGER,
)

def _escaped_like_fragment(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _escaped_contains_pattern(value: str) -> str:
    return f"%{_escaped_like_fragment(value)}%"


def _escaped_prefix_pattern(value: str) -> str:
    return f"{_escaped_like_fragment(value)}%"


def _safe_integer_token(token: str) -> int | None:
    if re.fullmatch(r"[+-]?\d+", token) is None:
        return None
    try:
        value = int(token)
    except ValueError:
        return None
    return value if MIN_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER else None


def _safe_decimal_token(token: str) -> Decimal | None:
    try:
        value = Decimal(token)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    _, digits, exponent = value.as_tuple()
    exponent_value = cast(int, exponent)
    fractional_digits = max(-exponent_value, 0)
    integer_digits = 0 if value.is_zero() else max(len(digits) + exponent_value, 0)
    if fractional_digits > MAX_DECIMAL_SCALE or integer_digits > MAX_DECIMAL_INTEGRAL_DIGITS:
        return None
    return value


def _search_predicate(token: str) -> ColumnElement[bool]:
    pattern = _escaped_contains_pattern(token)
    common = or_(
        Item.normalized_name.like(pattern, escape="\\"),
        Item.normalized_model.like(pattern, escape="\\"),
        exists(
            select(literal(1))
            .where(
                Manufacturer.id == Item.manufacturer_id,
                Manufacturer.normalized_name.like(pattern, escape="\\"),
            )
            .correlate(Item)
        ),
    )

    attribute_conditions: list[ColumnElement[bool]] = [
        ItemAttributeValue.text_value.ilike(pattern, escape="\\"),
        ItemAttributeValue.enum_value.ilike(pattern, escape="\\"),
    ]
    integer_value = _safe_integer_token(token)
    if integer_value is not None:
        attribute_conditions.append(ItemAttributeValue.integer_value == integer_value)
    decimal_value = _safe_decimal_token(token)
    if decimal_value is not None:
        attribute_conditions.append(ItemAttributeValue.decimal_value == decimal_value)
    if token in {"true", "false"}:
        attribute_conditions.append(ItemAttributeValue.boolean_value.is_(token == "true"))

    searchable_attribute = exists(
        select(literal(1))
        .select_from(ItemAttributeValue)
        .join(
            CategoryAttribute,
            CategoryAttribute.id == ItemAttributeValue.category_attribute_id,
        )
        .where(
            ItemAttributeValue.item_id == Item.id,
            CategoryAttribute.searchable.is_(True),
            or_(*attribute_conditions),
        )
        .correlate(Item)
    )
    return or_(common, searchable_attribute)


def _normalized_text_relevance(
    column: Any,
    token: str,
    *,
    exact: int,
    prefix: int,
    contains: int,
) -> Any:
    return case(
        (column == token, exact),
        (
            column.like(
                _escaped_prefix_pattern(token),
                escape="\\",
            ),
            prefix,
        ),
        (
            column.like(
                _escaped_contains_pattern(token),
                escape="\\",
            ),
            contains,
        ),
        else_=0,
    )


def _searchable_attribute_relevance(
    token: str,
) -> Any:
    exact_pattern = _escaped_like_fragment(
        token
    )
    prefix_pattern = _escaped_prefix_pattern(
        token
    )
    contains_pattern = (
        _escaped_contains_pattern(token)
    )

    weighted_matches: list[
        tuple[Any, int]
    ] = []

    integer_value = _safe_integer_token(
        token
    )

    if integer_value is not None:
        weighted_matches.append(
            (
                ItemAttributeValue.integer_value
                == integer_value,
                100,
            )
        )

    decimal_value = _safe_decimal_token(
        token
    )

    if decimal_value is not None:
        weighted_matches.append(
            (
                ItemAttributeValue.decimal_value
                == decimal_value,
                100,
            )
        )

    if token in {"true", "false"}:
        weighted_matches.append(
            (
                ItemAttributeValue.boolean_value.is_(
                    token == "true"
                ),
                100,
            )
        )

    weighted_matches.extend(
        [
            (
                or_(
                    ItemAttributeValue.text_value.ilike(
                        exact_pattern,
                        escape="\\",
                    ),
                    ItemAttributeValue.enum_value.ilike(
                        exact_pattern,
                        escape="\\",
                    ),
                ),
                100,
            ),
            (
                or_(
                    ItemAttributeValue.text_value.ilike(
                        prefix_pattern,
                        escape="\\",
                    ),
                    ItemAttributeValue.enum_value.ilike(
                        prefix_pattern,
                        escape="\\",
                    ),
                ),
                75,
            ),
            (
                or_(
                    ItemAttributeValue.text_value.ilike(
                        contains_pattern,
                        escape="\\",
                    ),
                    ItemAttributeValue.enum_value.ilike(
                        contains_pattern,
                        escape="\\",
                    ),
                ),
                45,
            ),
        ]
    )

    best_attribute_score = (
        select(
            func.max(
                case(
                    *weighted_matches,
                    else_=0,
                )
            )
        )
        .select_from(ItemAttributeValue)
        .join(
            CategoryAttribute,
            CategoryAttribute.id
            == ItemAttributeValue.category_attribute_id,
        )
        .where(
            ItemAttributeValue.item_id
            == Item.id,
            CategoryAttribute.searchable.is_(
                True
            ),
        )
        .correlate(Item)
        .scalar_subquery()
    )

    return func.coalesce(
        best_attribute_score,
        0,
    )


def _search_relevance_score(
    spec: CatalogQuerySpec,
) -> Any:
    score: Any = literal(0)

    for token in spec.tokens:
        score = (
            score
            + _normalized_text_relevance(
                Item.normalized_model,
                token,
                exact=160,
                prefix=120,
                contains=80,
            )
            + _normalized_text_relevance(
                Item.normalized_name,
                token,
                exact=150,
                prefix=110,
                contains=70,
            )
            + _normalized_text_relevance(
                Manufacturer.normalized_name,
                token,
                exact=120,
                prefix=90,
                contains=60,
            )
            + _searchable_attribute_relevance(
                token
            )
        )

    return score
