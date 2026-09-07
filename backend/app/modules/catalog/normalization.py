"""Shared technical identity rules for admin entry and workbook bootstrap."""

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from decimal import Decimal


def clean_text(value: str) -> str:
    return "\n".join(" ".join(line.split()) for line in value.strip().splitlines())


def identity_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def normalize_reach(value: str) -> int:
    """Parse supported distance clauses completely; never classify a partial parse."""
    text = clean_text(value).casefold()
    distance = r"(\d+(?:[.,]\d+)?)\s*(км|м)"
    found = list(re.finditer(distance + r"\b", text))
    if not found:
        raise ValueError("reach contains no supported distance")
    remainder = re.sub(distance + r"\b", "", text)
    remainder = re.sub(r"\b(?:om[1-5]|mmf|smf|rs-fec|до|без|с|по)\b", "", remainder)
    if re.sub(r"[\s:/;(),—–-]", "", remainder):
        raise ValueError("reach contains an unsupported or ambiguous clause")
    metres = [Decimal(m[1].replace(",", ".")) * (1000 if m[2] == "км" else 1) for m in found]
    if any(v <= 0 or v != v.to_integral_value() for v in metres):
        raise ValueError("reach must resolve to positive integer metres")
    return int(max(metres))


def item_signature(
    category_key: str,
    manufacturer: str | None,
    model: str | None,
    attributes: Mapping[str, object],
) -> str:
    normalized = {
        key: (
            identity_text(value)
            if isinstance(value, str)
            else str(value.normalize())
            if isinstance(value, Decimal)
            else value
        )
        for key, value in attributes.items()
        if value is not None and value != ""
    }
    content = [
        category_key,
        identity_text(manufacturer or ""),
        identity_text(model or ""),
        normalized,
    ]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
