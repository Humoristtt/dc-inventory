#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


def lifecycle_rule_prefix(
    rule: dict[str, Any],
) -> str | None:
    rule_filter = rule.get("Filter")

    if rule_filter is not None:
        if not isinstance(rule_filter, dict):
            return None

        if set(rule_filter) == {"Prefix"}:
            prefix = rule_filter.get("Prefix")
            return prefix if isinstance(prefix, str) else None

        if set(rule_filter) == {"And"}:
            and_filter = rule_filter.get("And")

            if (
                isinstance(and_filter, dict)
                and set(and_filter) == {"Prefix"}
            ):
                prefix = and_filter.get("Prefix")
                return (
                    prefix
                    if isinstance(prefix, str)
                    else None
                )

        # Filter has tag/size/additional conditions.
        # Such rule does not cover the whole configured prefix.
        return None

    # Legacy lifecycle API shape.
    legacy_prefix = rule.get("Prefix")

    if isinstance(legacy_prefix, str):
        return legacy_prefix

    return None


def require_rule_applies_to_prefix(
    rule: dict[str, Any],
    *,
    expected_prefix: str,
    rule_id: str,
) -> None:
    actual = lifecycle_rule_prefix(rule)

    if actual != expected_prefix:
        raise RuntimeError(
            f"Lifecycle rule {rule_id!r} does not apply "
            f"to the complete configured prefix "
            f"{expected_prefix!r}; resolved prefix={actual!r}"
        )
