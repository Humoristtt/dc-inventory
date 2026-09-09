from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.modules.catalog.query import _normalize_query_tokens, build_catalog_query_spec
from app.modules.catalog.service import CatalogValidationError


def test_search_token_budget_and_deduplication() -> None:
    assert _normalize_query_tokens("SFP sfp 10G") == ("sfp", "10g")
    assert len(_normalize_query_tokens(" ".join(str(i) for i in range(12)))) == 12
    with pytest.raises(CatalogValidationError, match="tokens"):
        _normalize_query_tokens(" ".join(str(i) for i in range(13)))


@pytest.mark.parametrize("field", ["manufacturer_ids", "location_ids", "filter_expressions"])
async def test_cardinality_rejected_before_database_access(field: str) -> None:
    db = AsyncMock()
    with pytest.raises(CatalogValidationError, match="50 values"):
        await build_catalog_query_spec(db, **cast(Any, {field: ["x"] * 51}))
    assert db.mock_calls == []


async def test_oversized_filter_rejected_before_database_access() -> None:
    db = AsyncMock()
    with pytest.raises(CatalogValidationError, match="2048"):
        await build_catalog_query_spec(db, filter_expressions=["x" * 2049])
    assert db.mock_calls == []
