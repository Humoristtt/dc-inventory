from __future__ import annotations

from app.core.idempotency import (
    advisory_lock_key,
    canonical_fingerprint,
    normalize_idempotency_key,
)


def test_normalize_idempotency_key_collapses_whitespace() -> None:
    assert normalize_idempotency_key("  alpha \t beta\n") == "alpha beta"
    assert normalize_idempotency_key(" \t\n ") == ""


def test_canonical_fingerprint_has_stable_unicode_golden_hash() -> None:
    payload = {
        "z": "ё",
        "a": [
            {"item_id": "2", "quantity": 1},
            {"item_id": "1", "quantity": 2},
        ],
    }

    assert canonical_fingerprint(payload) == (
        "e15b6627c250dc629b9fba247e199af8909bd2e2d6a1a7478d7a44296a4e647b"
    )
    assert canonical_fingerprint(
        {
            "a": payload["a"],
            "z": payload["z"],
        }
    ) == canonical_fingerprint(payload)
    assert canonical_fingerprint(
        {
            **payload,
            "z": "е",
        }
    ) != canonical_fingerprint(payload)


def test_advisory_lock_key_has_stable_signed_64_bit_golden_value() -> None:
    key = advisory_lock_key(
        "warehouse-idempotency",
        "00000000-0000-0000-0000-000000000001",
        "ключ",
    )

    assert key == -3475597476868392535
    assert -(2**63) <= key < 2**63
    assert advisory_lock_key(
        "warehouse-idempotency",
        "00000000-0000-0000-0000-000000000001",
        "ключ",
    ) == key
    assert advisory_lock_key(
        "warehouse-idempotency",
        "ключ",
        "00000000-0000-0000-0000-000000000001",
    ) != key
