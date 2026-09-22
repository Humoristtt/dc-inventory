"""Fail-closed historical Procurement identity upgrade regressions."""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.service import create_item, get_item_record
from tests.migration_helpers import alembic
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio
PREVIOUS = "f8b9c0d1e2f3"
CURRENT = "a9c0d1e2f3a4"


@pytest.mark.parametrize(
    "damage",
    [
        "forged_signature",
        "unknown_category",
        "unknown_attribute",
        "wrong_attribute_type",
        "missing_required_attribute",
        "malformed_decimal",
        "nonfinite_decimal",
        "invalid_manufacturer_type",
        "invalid_model_type",
        "invalid_attributes_shape",
        "blank_required_attribute",
    ],
)
async def test_a9_rejects_unverifiable_historical_snapshot(
    migration_database: str, damage: str
) -> None:
    url = migration_database
    alembic(url, "upgrade", PREVIOUS)
    engine = create_async_engine(url)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        item_id = await create_item(db, cable_payload())
        record = await get_item_record(db, item_id)
        snapshot: dict[str, Any] = {
            "category_key": record.category.key,
            "manufacturer_name": record.manufacturer.name if record.manufacturer else None,
            "model": record.item.model,
            "attributes": {
                key: str(value) if not isinstance(value, (bool, int, str)) else value
                for key, value in record.attributes.items()
            },
        }
        snapshot = deepcopy(snapshot)
        if damage == "forged_signature":
            snapshot["identity_signature"] = "f" * 64
            assert snapshot["identity_signature"] != record.item.identity_signature
        elif damage == "unknown_category":
            snapshot["category_key"] = "does_not_exist"
        elif damage == "unknown_attribute":
            snapshot["attributes"]["unknown_key"] = "unverified"
        elif damage == "wrong_attribute_type":
            # length_m is DECIMAL in cable fixtures; reject an object value.
            snapshot["attributes"]["length_m"] = {"not": "a decimal"}
        elif damage == "missing_required_attribute":
            snapshot["attributes"].pop("fiber")
        elif damage == "malformed_decimal":
            snapshot["attributes"]["length_m"] = "not-a-decimal"
        elif damage == "nonfinite_decimal":
            snapshot["attributes"]["length_m"] = "NaN"
        elif damage == "invalid_manufacturer_type":
            snapshot["manufacturer_name"] = {"not": "text"}
        elif damage == "invalid_model_type":
            snapshot["model"] = ["not", "text"]
        elif damage == "invalid_attributes_shape":
            snapshot["attributes"] = []
        elif damage == "blank_required_attribute":
            snapshot["attributes"]["fiber"] = "   "

        ids = [str(uuid.uuid4()) for _ in range(5)]
        initiator, manager, request, revision, line = ids
        await db.execute(
            text("""
                INSERT INTO users (id, role, access_status, approved_at)
                VALUES (CAST(:initiator AS uuid), 'ADMIN', 'APPROVED', now()),
                       (CAST(:manager AS uuid), 'MANAGER', 'APPROVED', now())
            """),
            {"initiator": initiator, "manager": manager},
        )
        await db.execute(
            text("""
                INSERT INTO procurement_requests (
                    id, request_number, status, initiator_user_id,
                    assigned_manager_user_id, creation_client_request_id,
                    request_fingerprint, current_revision_id, state_version
                ) VALUES (
                    CAST(:request AS uuid), :number, 'AGREEMENT_PENDING_MANAGER',
                    CAST(:initiator AS uuid), CAST(:manager AS uuid),
                    :client_key, :fingerprint, CAST(:revision AS uuid), 1
                )
            """),
            {"request": request, "number": "PR-A9-" + uuid.uuid4().hex[:12],
             "initiator": initiator, "manager": manager,
             "client_key": uuid.uuid4().hex, "fingerprint": "a" * 64,
             "revision": revision},
        )
        await db.execute(
            text("""
                INSERT INTO procurement_revisions (
                    id, request_id, revision_number, submitted_by_user_id,
                    submitted_by_display_name_snapshot, line_count
                ) VALUES (
                    CAST(:revision AS uuid), CAST(:request AS uuid), 1,
                    CAST(:initiator AS uuid), 'migration test', 1
                )
            """),
            {"revision": revision, "request": request, "initiator": initiator},
        )
        await db.execute(
            text("""
                INSERT INTO procurement_revision_lines (
                    id, revision_id, line_no, line_type, catalog_item_id,
                    display_snapshot, quantity
                ) VALUES (
                    CAST(:line AS uuid), CAST(:revision AS uuid), 1,
                    'EXISTING_ITEM', CAST(:item_id AS uuid),
                    CAST(:snapshot AS jsonb), 1
                )
            """),
            {"line": line, "revision": revision,
             "item_id": str(item_id),
             "snapshot": json.dumps(snapshot, ensure_ascii=False)},
        )
        await db.commit()
    await engine.dispose()

    # Tests cannot pass just because a9 never runs: check actual Alembic failure,
    # then prove transactional rollback left schema on f8 with no new column.
    output = alembic(url, "upgrade", CURRENT, success=False)
    assert any(marker in output for marker in (
        "cannot safely reconstruct canonical identity",
        "DataError",
        "invalid input syntax for type numeric",
    )), output
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        column_exists = await connection.scalar(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'procurement_revision_lines'
                  AND column_name = 'expected_identity_signature'
            )
        """))
    await engine.dispose()
    assert version == PREVIOUS
    assert column_exists is False
