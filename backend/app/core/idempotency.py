from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def normalize_idempotency_key(value: str) -> str:
    """Collapse surrounding/internal whitespace without applying domain policy."""
    return " ".join(value.split())


def canonical_fingerprint(payload: Mapping[str, object]) -> str:
    """Return the shared deterministic SHA-256 fingerprint for a JSON object."""
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def advisory_lock_key(namespace: str, *parts: object) -> int:
    """Derive the signed 64-bit PostgreSQL advisory-lock key used by domains."""
    value = "|".join(
        [namespace, *(str(part) for part in parts)]
    )
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=True,
    )
