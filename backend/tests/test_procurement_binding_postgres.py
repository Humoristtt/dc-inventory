"""Procurement identity must remain bound to the approved revision."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.errors import postgres_sqlstate
from app.modules.catalog.models import Item
from app.modules.catalog.schemas import ItemCreate, ItemPatch
from app.modules.catalog.service import create_item, update_item
from app.modules.identity.enums import UserRole
from app.modules.identity.models import User
from app.modules.inventory.schemas import LocationCreate
from app.modules.inventory.service import create_location
from app.modules.procurement.enums import ProcurementLineType
from app.modules.procurement.schemas import (
    ExistingItemLineCreate,
    LineBindingCreate,
    ProcurementAcceptanceCreate,
    ProcurementRequestCreate,
    ProposedItemCreateAndBind,
    ProposedItemLineCreate,
)
from app.modules.procurement.service import (
    ProcurementConflictError,
    ProcurementRecord,
    bind_line,
    complete_acceptance,
    create_and_bind_line,
    create_request,
)
from tests.migration_helpers import alembic
from tests.test_procurement_postgres import move_to_acceptance, seed_procurement, settings
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


async def proposed_request(
    db: AsyncSession,
) -> tuple[ProcurementRecord, User, ItemCreate]:
    initiator, _ = await actor(db, UserRole.ADMIN)
    manager, _ = await actor(db, UserRole.MANAGER)
    acceptor, _ = await actor(db, UserRole.SENIOR_ENGINEER)
    item = cable_payload()
    record = await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager.id,
            client_request_id=uuid.uuid4().hex,
            lines=[
                ProposedItemLineCreate(
                    line_type=ProcurementLineType.PROPOSED_ITEM,
                    category_key=item.category_key,
                    manufacturer_id=item.manufacturer_id,
                    name=item.name,
                    model=item.model,
                    attributes=item.attributes,
                    quantity=1,
                )
            ],
        ),
        actor_user_id=initiator.id,
        settings=settings(),
    )
    return record, acceptor, item


async def test_a9_existing_line_stores_approved_signature(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    *_, item_id, _location, record = await seed_procurement(db)
    item = await db.get(Item, item_id)
    assert item is not None
    assert record.current_revision.lines[0].expected_identity_signature == item.identity_signature


async def test_a9_bind_rejects_different_catalog_identity(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    record, acceptor, _approved_item = await proposed_request(db)
    candidate_id = await create_item(db, cable_payload())
    line = record.current_revision.lines[0]
    candidate = await db.get(Item, candidate_id)
    assert candidate is not None
    assert candidate.identity_signature != line.expected_identity_signature

    with pytest.raises(ProcurementConflictError) as raised:
        await bind_line(
            db,
            record.request.id,
            LineBindingCreate(
                expected_state_version=record.request.state_version,
                expected_revision_id=record.request.current_revision_id,
                client_request_id=uuid.uuid4().hex,
                line_id=line.id,
                item_id=candidate_id,
            ),
            actor_user_id=acceptor.id,
        )
    assert raised.value.code == "item_identity_mismatch"
    assert line.binding is None


async def test_a9_create_and_bind_rejects_mismatched_item_without_commit(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    record, acceptor, _approved_item = await proposed_request(db)
    line = record.current_revision.lines[0]
    count_before = await db.scalar(select(func.count(Item.id)))

    # A transaction/savepoint boundary is necessary: the service must raise
    # before acceptance; the caller owns rollback of a failed transaction.
    with pytest.raises(ProcurementConflictError) as raised:
        async with db.begin_nested():
            await create_and_bind_line(
                db,
                record.request.id,
                ProposedItemCreateAndBind(
                    expected_state_version=record.request.state_version,
                    expected_revision_id=record.request.current_revision_id,
                    client_request_id=uuid.uuid4().hex,
                    line_id=line.id,
                    item=cable_payload(),
                ),
                actor_user_id=acceptor.id,
            )
    assert raised.value.code == "item_identity_mismatch"
    assert await db.scalar(select(func.count(Item.id))) == count_before


async def test_a9_create_and_bind_accepts_exact_approved_item(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    record, acceptor, approved_item = await proposed_request(db)
    line = record.current_revision.lines[0]
    updated = await create_and_bind_line(
        db,
        record.request.id,
        ProposedItemCreateAndBind(
            expected_state_version=record.request.state_version,
            expected_revision_id=record.request.current_revision_id,
            client_request_id=uuid.uuid4().hex,
            line_id=line.id,
            item=approved_item,
        ),
        actor_user_id=acceptor.id,
    )
    bound = updated.current_revision.lines[0].binding
    assert bound is not None
    created = await db.get(Item, bound.item_id)
    assert created is not None
    assert created.identity_signature == line.expected_identity_signature


async def test_a9_receipt_rejects_existing_item_mutated_after_approval(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    _initiator, manager, senior, item_id, location, record = await seed_procurement(db)
    record = await move_to_acceptance(db, record, manager_id=manager.id)

    # This is an ordinary, valid Catalog update, not a forged signature.
    await update_item(
        db,
        item_id,
        ItemPatch(model="different model after procurement approval"),
        fields_set={"model"},
    )

    with pytest.raises(ProcurementConflictError) as raised:
        await complete_acceptance(
            db,
            record.request.id,
            ProcurementAcceptanceCreate(
                expected_state_version=record.request.state_version,
                expected_revision_id=record.request.current_revision_id,
                client_request_id=uuid.uuid4().hex,
                receiving_location_id=location.id,
            ),
            actor_user_id=senior.id,
            settings=settings(),
        )
    assert raised.value.code == "item_identity_mismatch"
    assert record.request.final_movement_id is None


async def test_a9_receipt_rejects_bound_proposed_item_mutated_after_binding(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    record, acceptor, approved_item = await proposed_request(db)
    line = record.current_revision.lines[0]
    record = await create_and_bind_line(
        db,
        record.request.id,
        ProposedItemCreateAndBind(
            expected_state_version=record.request.state_version,
            expected_revision_id=record.request.current_revision_id,
            client_request_id=uuid.uuid4().hex,
            line_id=line.id,
            item=approved_item,
        ),
        actor_user_id=acceptor.id,
    )
    binding = record.current_revision.lines[0].binding
    assert binding is not None
    record = await move_to_acceptance(
        db, record, manager_id=record.request.assigned_manager_user_id
    )
    location = await create_location(
        db,
        LocationCreate(
            code=uuid.uuid4().hex,
            name="a9 isolated receipt regression",
            location_type="WAREHOUSE",
        ),
    )
    await update_item(
        db,
        binding.item_id,
        ItemPatch(model="catalog item changed after binding"),
        fields_set={"model"},
    )
    with pytest.raises(ProcurementConflictError) as raised:
        await complete_acceptance(
            db,
            record.request.id,
            ProcurementAcceptanceCreate(
                expected_state_version=record.request.state_version,
                expected_revision_id=record.request.current_revision_id,
                client_request_id=uuid.uuid4().hex,
                receiving_location_id=location.id,
            ),
            actor_user_id=acceptor.id,
            settings=settings(),
        )
    assert raised.value.code == "item_identity_mismatch"
    assert record.request.final_movement_id is None


async def test_a9_existing_snapshot_holds_item_lock_until_transaction_end(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", "head")
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as seed:
            initiator, _ = await actor(seed, UserRole.ADMIN)
            manager, _ = await actor(seed, UserRole.MANAGER)
            item_id = await create_item(seed, cable_payload())
            await seed.commit()

        async with AsyncSession(engine, expire_on_commit=False) as creator:
            await create_request(
                creator,
                ProcurementRequestCreate(
                    assigned_manager_user_id=manager.id,
                    client_request_id=uuid.uuid4().hex,
                    lines=[
                        ExistingItemLineCreate(
                            line_type=ProcurementLineType.EXISTING_ITEM,
                            item_id=item_id,
                            quantity=1,
                        )
                    ],
                ),
                actor_user_id=initiator.id,
                settings=settings(),
            )
            # FOR NO KEY UPDATE is compatible with an FK's KEY SHARE lock.
            # Only the explicit identity-protecting row lock blocks this NOWAIT.
            async with engine.connect() as contender:
                with pytest.raises(DBAPIError) as raised:
                    await contender.execute(
                        text(
                            "SELECT id FROM items "
                            "WHERE id = CAST(:item_id AS uuid) "
                            "FOR NO KEY UPDATE NOWAIT"
                        ),
                        {"item_id": str(item_id)},
                    )
                assert postgres_sqlstate(raised.value) == "55P03"
            await creator.rollback()
    finally:
        await engine.dispose()
