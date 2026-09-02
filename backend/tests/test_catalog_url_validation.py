from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.catalog.schemas import ItemCreate, ItemPatch


def test_item_create_canonicalizes_datasheet_url() -> None:
    payload = ItemCreate(
        category_key="sfp",
        name="Test SFP",
        datasheet_url="  https://Example.COM/docs?q=a  b  ",
    )

    assert payload.datasheet_url == (
        "https://example.com/docs?q=a%20%20b"
    )


def test_item_patch_canonicalizes_datasheet_url() -> None:
    payload = ItemPatch(
        datasheet_url="  HTTPS://Example.COM/updated path  ",
    )

    assert payload.datasheet_url == (
        "https://example.com/updated%20path"
    )


def test_blank_datasheet_url_becomes_none() -> None:
    payload = ItemPatch(datasheet_url="   \t  ")

    assert payload.datasheet_url is None


@pytest.mark.parametrize(
    "value",
    [
        "ftp://example.com/file",
        "javascript:alert(1)",
        "not-a-url",
    ],
)
def test_datasheet_url_rejects_non_http_values(value: str) -> None:
    with pytest.raises(ValidationError):
        ItemPatch(datasheet_url=value)
