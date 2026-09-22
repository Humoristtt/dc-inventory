"""Fail-closed upgrade checks for untrustworthy pre-a9 procurement snapshots."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.migration_helpers import alembic

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("forged_signature", [False, True])
async def test_a9_rejects_unreconstructable_historical_identity_and_rolls_back(
    migration_database: str,
    forged_signature: bool,
) -> None:
    url = migration_database
    alembic(url, "upgrade", "f8b9c0d1e2f3")

    request_id = str(uuid.uuid4())
    revision_id = str(uuid.uuid4())
    line_id = str(uuid.uuid4())
    initiator_id = str(uuid.uuid4())
    manager_id = str(uuid.uuid4())

    # A valid-looking digest must not be trusted when the approved snapshot
    # cannot independently be reconstructed (unknown category, no attributes).
    snapshot: dict[str, object] = {
        "category_key": "a9-invalid-category-that-does-not-exist",
        "manufacturer_name": None,
        "model": "Unverified historical model",
        "attributes": {},
    }
    if forged_signature:
        snapshot["identity_signature"] = "f" * 64

    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            for user_id, role in ((initiator_id, "ADMIN"), (manager_id, "MANAGER")):
                await db.execute(
                    text(
                        """
                        INSERT INTO users (id, role, access_status, approved_at)
                        VALUES (CAST(:id AS uuid), :role, 'APPROVED', now())
                        """
                    ),
                    {"id": user_id, "role": role},
                )

            await db.execute(
                text(
                    """
                    INSERT INTO procurement_requests (
                        id, request_number, status, initiator_user_id,
                        assigned_manager_user_id, creation_client_request_id,
                        request_fingerprint, current_revision_id, state_version
                    ) VALUES (
                        CAST(:request_id AS uuid), :request_number,
                        'AGREEMENT_PENDING_MANAGER', CAST(:initiator_id AS uuid),
                        CAST(:manager_id AS uuid), :client_request_id,
                        :request_fingerprint, CAST(:revision_id AS uuid), 1
                    )
                    """
                ),
                {
                    "request_id": request_id,
                    "request_number": "PR-A9-NEG-" + uuid.uuid4().hex[:12],
                    "initiator_id": initiator_id,
                    "manager_id": manager_id,
                    "client_request_id": "a9-negative-" + uuid.uuid4().hex,
                    "request_fingerprint": "a" * 64,
                    "revision_id": revision_id,
                },
            )
            await db.execute(
                text(
                    """
                    INSERT INTO procurement_revisions (
                        id, request_id, revision_number, submitted_by_user_id,
                        submitted_by_display_name_snapshot, general_comment, line_count
                    ) VALUES (
                        CAST(:revision_id AS uuid), CAST(:request_id AS uuid), 1,
                        CAST(:initiator_id AS uuid), 'A9 historical actor', NULL, 1
                    )
                    """
                ),
                {
                    "revision_id": revision_id,
                    "request_id": request_id,
                    "initiator_id": initiator_id,
                },
            )
            await db.execute(
                text(
                    """
                    INSERT INTO procurement_revision_lines (
                        id, revision_id, line_no, line_type, catalog_item_id,
                        display_snapshot, quantity
                    ) VALUES (
                        CAST(:line_id AS uuid), CAST(:revision_id AS uuid), 1,
                        'PROPOSED_ITEM', NULL, CAST(:snapshot AS jsonb), 1
                    )
                    """
                ),
                {
                    "line_id": line_id,
                    "revision_id": revision_id,
                    "snapshot": json.dumps(snapshot, ensure_ascii=False),
                },
            )
            await db.commit()
    finally:
        await engine.dispose()

    output = alembic(url, "upgrade", "a9c0d1e2f3a4", success=False)
    assert "cannot safely reconstruct canonical identity" in output

    # Alembic failure must not leave a partially applied DDL or disabled
    # immutable-history trigger behind.
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "f8b9c0d1e2f3"
            )
            count = await connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'procurement_revision_lines'
                      AND column_name = 'expected_identity_signature'
                    """
                )
            )
            assert count == 0
            trigger_enabled = await connection.scalar(
                text(
                    """
                    SELECT t.tgenabled
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    WHERE c.relname = 'procurement_revision_lines'
                      AND t.tgname = 'trg_procurement_revision_lines_append_only'
                    """
                )
            )
            assert trigger_enabled in {b"O", b"A", "O", "A"}
    finally:
        await engine.dispose()
