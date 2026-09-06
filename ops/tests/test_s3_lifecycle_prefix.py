#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT / "ops/backup"),
)

from lifecycle_policy import (  # noqa: E402
    lifecycle_rule_prefix,
    require_rule_applies_to_prefix,
)


PREFIX = "postgres/"


def accept(rule: dict) -> None:
    require_rule_applies_to_prefix(
        rule,
        expected_prefix=PREFIX,
        rule_id="test-rule",
    )


def reject(rule: dict) -> None:
    try:
        require_rule_applies_to_prefix(
            rule,
            expected_prefix=PREFIX,
            rule_id="test-rule",
        )
    except RuntimeError:
        return

    raise AssertionError(
        f"unsafe lifecycle rule was accepted: {rule!r}"
    )


# Current AWS/Boto3 direct Prefix filter.
direct = {
    "Filter": {
        "Prefix": "postgres/",
    },
}
accept(direct)
assert lifecycle_rule_prefix(direct) == PREFIX


# Legacy API form.
legacy = {
    "Prefix": "postgres/",
}
accept(legacy)
assert lifecycle_rule_prefix(legacy) == PREFIX


# Semantically exact And form is also acceptable.
and_prefix = {
    "Filter": {
        "And": {
            "Prefix": "postgres/",
        },
    },
}
accept(and_prefix)


# Wrong prefix.
reject(
    {
        "Filter": {
            "Prefix": "other/",
        },
    }
)


# Empty/global rule must not satisfy postgres-only policy.
reject(
    {
        "Filter": {},
    }
)


# Tags restrict the rule to only a subset of the prefix.
reject(
    {
        "Filter": {
            "And": {
                "Prefix": "postgres/",
                "Tags": [
                    {
                        "Key": "class",
                        "Value": "backup",
                    },
                ],
            },
        },
    }
)


# Object-size conditions also restrict the rule to a subset.
reject(
    {
        "Filter": {
            "Prefix": "postgres/",
            "ObjectSizeGreaterThan": 1024,
        },
    }
)


# Tag-only lifecycle rule is not a prefix rule.
reject(
    {
        "Filter": {
            "Tag": {
                "Key": "class",
                "Value": "backup",
            },
        },
    }
)


# Missing filter/prefix.
reject({})


print("AUD_03_LIFECYCLE_PREFIX_CONTRACT=PASS")
