import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.catalog.normalization import item_signature
from app.modules.catalog.service import create_item, get_item_record
from tests.migration_helpers import alembic
from tests.warehouse_helpers import cable_payload

PREVIOUS_HEAD = "f8b9c0d1e2f3"
CURRENT_HEAD = "a9c0d1e2f3a4"

pytestmark = pytest.mark.asyncio


def snapshot_value(
    value: str | int | Decimal | bool,
) -> str | int | bool:
    if isinstance(value, Decimal):
        return str(value)
    return value


async def test_cp04_historical_existing_line_uses_approved_snapshot_identity(
    migration_database: str,
) -> None:
    url = migration_database

    alembic(
        url,
        "upgrade",
        PREVIOUS_HEAD,
    )

    engine = create_async_engine(url)

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        item_id = await create_item(
            db,
            cable_payload(),
        )

        record = await get_item_record(
            db,
            item_id,
        )

        current_signature = record.item.identity_signature

        approved_model = "CP04 historical approved model"

        approved_signature = item_signature(
            record.category.key,
            (record.manufacturer.name if record.manufacturer is not None else None),
            approved_model,
            record.attributes,
        )

        assert approved_signature != current_signature

        snapshot = {
            "category_key": record.category.key,
            "category_name": record.category.display_name,
            "manufacturer_id": (
                str(record.manufacturer.id) if record.manufacturer is not None else None
            ),
            "manufacturer_name": (
                record.manufacturer.name if record.manufacturer is not None else None
            ),
            "name": record.item.name,
            "model": approved_model,
            "attributes": {key: snapshot_value(value) for key, value in record.attributes.items()},
        }

        initiator_id = str(
            await db.scalar(
                text(
                    """
                    INSERT INTO users (
                        id,
                        role,
                        access_status,
                        approved_at
                    )
                    VALUES (
                        gen_random_uuid(),
                        'ADMIN',
                        'APPROVED',
                        now()
                    )
                    RETURNING id
                    """
                )
            )
        )

        manager_id = str(
            await db.scalar(
                text(
                    """
                    INSERT INTO users (
                        id,
                        role,
                        access_status,
                        approved_at
                    )
                    VALUES (
                        gen_random_uuid(),
                        'MANAGER',
                        'APPROVED',
                        now()
                    )
                    RETURNING id
                    """
                )
            )
        )

        request_id = str(uuid.uuid4())
        revision_id = str(uuid.uuid4())
        line_id = str(uuid.uuid4())

        await db.execute(
            text(
                """
                INSERT INTO procurement_requests (
                    id,
                    request_number,
                    status,
                    initiator_user_id,
                    assigned_manager_user_id,
                    creation_client_request_id,
                    request_fingerprint,
                    current_revision_id,
                    state_version
                )
                VALUES (
                    :request_id,
                    :request_number,
                    'AGREEMENT_PENDING_MANAGER',
                    :initiator_id,
                    :manager_id,
                    :client_request_id,
                    :request_fingerprint,
                    :revision_id,
                    1
                )
                """
            ),
            {
                "request_id": request_id,
                "request_number": ("PR-CP04-HIST-" + uuid.uuid4().hex[:12]),
                "initiator_id": initiator_id,
                "manager_id": manager_id,
                "client_request_id": ("cp04-historical-" + uuid.uuid4().hex),
                "request_fingerprint": "f" * 64,
                "revision_id": revision_id,
            },
        )

        await db.execute(
            text(
                """
                INSERT INTO procurement_revisions (
                    id,
                    request_id,
                    revision_number,
                    submitted_by_user_id,
                    submitted_by_display_name_snapshot,
                    general_comment,
                    line_count
                )
                VALUES (
                    :revision_id,
                    :request_id,
                    1,
                    :initiator_id,
                    'CP04 historical actor',
                    NULL,
                    1
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
                    id,
                    revision_id,
                    line_no,
                    line_type,
                    catalog_item_id,
                    display_snapshot,
                    quantity
                )
                VALUES (
                    :line_id,
                    :revision_id,
                    1,
                    'EXISTING_ITEM',
                    :item_id,
                    CAST(:snapshot AS jsonb),
                    1
                )
                """
            ),
            {
                "line_id": line_id,
                "revision_id": revision_id,
                "item_id": str(item_id),
                "snapshot": json.dumps(
                    snapshot,
                    ensure_ascii=False,
                ),
            },
        )

        await db.commit()

    await engine.dispose()

    alembic(
        url,
        "upgrade",
        CURRENT_HEAD,
    )

    engine = create_async_engine(url)

    async with engine.connect() as db:
        assert (
            await db.scalar(
                text(
                    """
                    SELECT version_num
                    FROM alembic_version
                    """
                )
            )
            == CURRENT_HEAD
        )

        migrated_signature = await db.scalar(
            text(
                """
                    SELECT
                        expected_identity_signature
                    FROM procurement_revision_lines
                    WHERE id = :line_id
                    """
            ),
            {
                "line_id": line_id,
            },
        )

    await engine.dispose()

    assert migrated_signature == approved_signature, (
        "historical Procurement identity "
        "must come from the immutable "
        "approved display_snapshot, not "
        "from the current Catalog Item; "
        f"approved={approved_signature}, "
        f"current={current_signature}, "
        f"migrated={migrated_signature}"
    )

    assert migrated_signature != current_signature
